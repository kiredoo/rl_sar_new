/*
Find execution time for multiple functions.
This is an extension of ebpf_et.c.

Known limitation:
- The functions that going to be profiled must be mutually exclusive.
If two functions are overlapped, such as A calls B, it is difficult to tell
whether the syscalls should contribute to A or not.

Since the program is designed for autoware.universe' callback functions,
where each of them are mutually exclusive,
we can safely use this program to measure their execution time.
*/

#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

#define MAX_NUM_SAMPLES 3000
#define CB_STACK_MAX 8

/* ---------------- key types ---------------- */
struct key_t {
  u32 tid;    // low 32 bits of pid_tgid = TID
  s32 cb_id;  // template assigns stable id via loop.index0
};

struct cb_stack_t {
  s32 id[CB_STACK_MAX];
  u32 depth;
};

/* ---------------- per-thread (tid64) state ---------------- */
BPF_HASH(g_sys_nesting, u64, u32, 16384);             // tid64 -> nesting count across ANY callback (gate syscalls)
BPF_HASH(g_syscall_start_time_dict, u64, u64, 16384); // tid64 -> current syscall start ns
BPF_HASH(g_cb_stack, u64, struct cb_stack_t, 8192);   // tid64 -> stack of active cb_id (top = current)

/* ---------------- per-(tid,cb) callback timing state ---------------- */
BPF_HASH(g_cb_start_ns, struct key_t, u64, 16384);    // (tid,cb) -> outermost start ns for THIS callback
BPF_HASH(g_cb_inflight, struct key_t, u32, 16384);    // (tid,cb) -> nesting for THIS callback

/* ---------------- syscall accounting ----------------
   g_cb_sys_acc: accumulated syscall time per (tid, cb), continuously increased at syscall_out
   g_cb_sysacc_snap: snapshot of g_cb_sys_acc taken at THIS callback's outermost enter, used for per-sample delta
*/
BPF_HASH(g_cb_sys_acc, struct key_t, u64, 16384);     // (tid,cb) -> accumulated syscall ns
BPF_HASH(g_cb_sysacc_snap, struct key_t, u64, 16384); // (tid,cb) -> snapshot at outermost enter

/* ---------------- helpers: per-tid syscall accumulation primitives ---------------- */
static __always_inline void log_syscall_start_time(u64 tid64) {
  u64 now = bpf_ktime_get_ns();
  g_syscall_start_time_dict.update(&tid64, &now);
}

static __always_inline u64 calc_this_syscall_duration(u64 tid64) {
  u64 *st = g_syscall_start_time_dict.lookup(&tid64);
  if (st && (*st > 0)) {
    u64 dur = bpf_ktime_get_ns() - *st;
    *st = 0;
    return dur;
  }
  return 0;
}

static __always_inline int should_accumulate_syscall_time(u64 tid64) {
  u32 *nest = g_sys_nesting.lookup(&tid64);
  return (nest && (*nest > 0)) ? 1 : 0;
}

/* ---------------- helpers: per-tid cb stack ---------------- */
static __always_inline void cb_stack_push(u64 tid64, s32 cb_id) {
  struct cb_stack_t st = {};
  struct cb_stack_t *pst = g_cb_stack.lookup(&tid64);
  if (pst) {
    st = *pst;
  }

  if (st.depth < CB_STACK_MAX) {
    u32 d = st.depth;
    if (d == 0) st.id[0] = cb_id;
    else if (d == 1) st.id[1] = cb_id;
    else if (d == 2) st.id[2] = cb_id;
    else if (d == 3) st.id[3] = cb_id;
    else if (d == 4) st.id[4] = cb_id;
    else if (d == 5) st.id[5] = cb_id;
    else if (d == 6) st.id[6] = cb_id;
    else if (d == 7) st.id[7] = cb_id;

    st.depth = d + 1;
    g_cb_stack.update(&tid64, &st);
  }
}

static __always_inline void cb_stack_pop(u64 tid64) {
  struct cb_stack_t *pst = g_cb_stack.lookup(&tid64);
  if (pst && pst->depth > 0) {
    u32 d = pst->depth - 1;
    pst->depth = d;
    g_cb_stack.update(&tid64, pst);
  }
}

static __always_inline int cb_stack_top(u64 tid64, s32 *out_cb_id) {
  struct cb_stack_t *pst = g_cb_stack.lookup(&tid64);
  if (!(pst && pst->depth > 0)) return 0;

  u32 d = pst->depth - 1;  /* 0..7 */
  if (d >= CB_STACK_MAX) return 0;

  s32 v = -1;
  if      (d == 0) v = pst->id[0];
  else if (d == 1) v = pst->id[1];
  else if (d == 2) v = pst->id[2];
  else if (d == 3) v = pst->id[3];
  else if (d == 4) v = pst->id[4];
  else if (d == 5) v = pst->id[5];
  else if (d == 6) v = pst->id[6];
  else if (d == 7) v = pst->id[7];

  if (v < 0) return 0;
  *out_cb_id = v;
  return 1;
}
/* ---------------- helpers: callback enter/exit ---------------- */
static __always_inline void cb_enter(s32 cb_id) {
  u64 tid64 = bpf_get_current_pid_tgid();
  u32 tid = (u32)tid64;
  struct key_t k = { .tid = tid, .cb_id = cb_id };

  /* inflight++ for THIS callback */
  u32 *pin = g_cb_inflight.lookup(&k);
  if (pin) {
    u32 v = *pin + 1;
    g_cb_inflight.update(&k, &v);
  } else {
    u32 one = 1;
    g_cb_inflight.update(&k, &one);
    /* first (outermost) enter: record start and snapshot per-cb sysacc */
    u64 now = bpf_ktime_get_ns();
    g_cb_start_ns.update(&k, &now);
    u64 zero = 0, *acc = g_cb_sys_acc.lookup_or_try_init(&k, &zero);
    u64 snap = acc ? *acc : 0;
    g_cb_sysacc_snap.update(&k, &snap);
  }

  /* per-tid nesting++ (syscall gating) */
  u32 *ptn = g_sys_nesting.lookup(&tid64);
  if (ptn) {
    u32 v = *ptn + 1;
    g_sys_nesting.update(&tid64, &v);
  } else {
    u32 one = 1;
    g_sys_nesting.update(&tid64, &one);
  }

  /* push cb_id to per-tid stack */
  cb_stack_push(tid64, cb_id);
}

static __always_inline u64 cb_exit_outermost_and_get_resp_ns(s32 cb_id, u64 *out_sys_delta_ns) {
  u64 tid64 = bpf_get_current_pid_tgid();
  u32 tid = (u32)tid64;
  struct key_t k = { .tid = tid, .cb_id = cb_id };

  u64 resp_ns = 0;
  if (out_sys_delta_ns) *out_sys_delta_ns = 0;

  /* inflight-- for THIS callback */
  u32 *pin = g_cb_inflight.lookup(&k);
  if (pin) {
    if (*pin <= 1) {
      /* outermost exit: compute response time, and per-cb syscall delta */
      u64 *st = g_cb_start_ns.lookup(&k);
      if (st && (*st > 0)) {
        resp_ns = bpf_ktime_get_ns() - *st;
      }
      g_cb_start_ns.delete(&k);
      g_cb_inflight.delete(&k);

      /* compute per-cb syscall delta: (cur_acc - snap) */
      u64 zero = 0, *acc = g_cb_sys_acc.lookup_or_try_init(&k, &zero);
      u64 cur = acc ? *acc : 0;
      u64 *snap = g_cb_sysacc_snap.lookup(&k);
      u64 base = snap ? *snap : 0;
      if (out_sys_delta_ns) {
        *out_sys_delta_ns = (cur >= base) ? (cur - base) : 0;
      }
      g_cb_sysacc_snap.delete(&k);
    } else {
      /* inner exit: just dec inflight */
      u32 v = *pin - 1;
      g_cb_inflight.update(&k, &v);
    }
  }

  /* per-tid nesting-- (syscall gating) */
  u32 *ptn = g_sys_nesting.lookup(&tid64);
  if (ptn) {
    if (*ptn <= 1) {
      g_sys_nesting.delete(&tid64);
    } else {
      u32 v = *ptn - 1;
      g_sys_nesting.update(&tid64, &v);
    }
  }

  /* pop stack */
  cb_stack_pop(tid64);

  return resp_ns;
}

/* ---------------- per-callback sample buffers ---------------- */
{% for demangled_name, loc in cb_locs.items() %}

BPF_ARRAY(g_response_times_ns_{{loc.mangled_name}}, u64, MAX_NUM_SAMPLES);
BPF_ARRAY(g_syscall_times_ns_{{loc.mangled_name}}, u64, MAX_NUM_SAMPLES);  // per-sample syscall delta for THIS cb
BPF_ARRAY(g_num_samples_{{loc.mangled_name}}, s32, 1);

static __always_inline s32 get_sampling_index_{{loc.mangled_name}}() {
  s32 zero = 0;
  s32 *val = g_num_samples_{{loc.mangled_name}}.lookup(&zero);
  return val ? *val : MAX_NUM_SAMPLES;
}

/* ---------------- handlers for this callback ---------------- */
int cb_in_{{loc.mangled_name}}(struct pt_regs *ctx) {
  s32 sidx = get_sampling_index_{{loc.mangled_name}}();
  if (sidx < MAX_NUM_SAMPLES) {
    cb_enter({{ loop.index0 }});
  }
  return 0;
}

int cb_out_{{loc.mangled_name}}(struct pt_regs *ctx) {
  s32 sidx = get_sampling_index_{{loc.mangled_name}}();
  if (sidx < MAX_NUM_SAMPLES) {
    u64 sys_delta_ns = 0;
    u64 resp_ns = cb_exit_outermost_and_get_resp_ns({{ loop.index0 }}, &sys_delta_ns);

    g_response_times_ns_{{loc.mangled_name}}.update(&sidx, &resp_ns);
    g_syscall_times_ns_{{loc.mangled_name}}.update(&sidx, &sys_delta_ns);
    g_num_samples_{{loc.mangled_name}}.increment(0);
  }
  return 0;
}
{% endfor %}

/* ---------------- syscall hooks ----------------
   Attribute each syscall duration to the current active cb on this tid (stack top).
*/
int syscall_in(struct pt_regs *ctx) {
  u64 tid64 = bpf_get_current_pid_tgid();
  if (should_accumulate_syscall_time(tid64)) {
    log_syscall_start_time(tid64);
  }
  return 0;
}

int syscall_out(struct pt_regs *ctx) {
  u64 tid64 = bpf_get_current_pid_tgid();
  if (should_accumulate_syscall_time(tid64)) {
    u64 dur = calc_this_syscall_duration(tid64);
    if (dur) {
      s32 top_id = -1;
      if (cb_stack_top(tid64, &top_id) && top_id >= 0) {
        struct key_t k = { .tid = (u32)tid64, .cb_id = top_id };
        u64 zero = 0, *acc = g_cb_sys_acc.lookup_or_try_init(&k, &zero);
        if (acc) *acc += dur;  // attribute syscall to the active cb
      }
    }
  }
  return 0;
}
