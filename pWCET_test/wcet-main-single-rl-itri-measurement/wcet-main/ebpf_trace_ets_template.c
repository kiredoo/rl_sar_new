#include <linux/mm_types.h>
#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

// clang-format off
#define MAX_NUM_CALLBACKS {{ cb_locs | length }}
// clang-format on

/*
kernel space                                                                  user space
------------------------------------------------------------------------------------------
pid, per-thread id, bpf_get_current_pid_tgid() & 0xffffffff                  tid, gettid()
tgid, bpf_get_current_pid_tgid() >> 32                                       pid, getpid()
*/

struct trace_event_t
{
  /*
  ts in chrome://tracing is microseconds. Since eBPF cannot handle floating points,
  we use nanoseconds here and let the Python frontend to convert it to microseconds;
  */
  u64 ts_in_ns;
  u64 dur_in_ns;  // duration
  u32 cpu;
  u32 tgid;  // user space process id, getpid()
  u32 pid;   // user space thread id, gettid()
  s32 cb_index;
  u8 is_cb_event;
  u8 is_valid;
};

BPF_RINGBUF_OUTPUT(g_trace_event_rbo, 8);                   // 8 pages
BPF_HASH(g_pid_to_trace_event, u32, struct trace_event_t);  // pid -> struct trace_event_t
BPF_HASH(g_pid_to_sched_event, u32, struct trace_event_t);

static u32 _is_cb_running(u32 pid)
{
  struct trace_event_t * obj = g_pid_to_trace_event.lookup(&pid);
  if (obj && obj->is_valid && (obj->cb_index < MAX_NUM_CALLBACKS)) {
    return 1;
  } else {
    return 0;
  }
}

static void _handle_beginning_of_context_switch(u32 pid)
{
  u64 pid_tgid = bpf_get_current_pid_tgid();
  u32 tgid = pid_tgid >> 32;

  struct trace_event_t ev = {0};
  struct trace_event_t * obj = g_pid_to_sched_event.lookup_or_try_init(&pid, &ev);
  if (obj) {
    obj->tgid = tgid;
    obj->pid = pid;
    obj->ts_in_ns = bpf_ktime_get_ns();
    obj->dur_in_ns = 0;
    obj->cpu = bpf_get_smp_processor_id();
    obj->is_cb_event = 0;
    obj->is_valid = 1;
    obj->cb_index = MAX_NUM_CALLBACKS;
  }
}

static void _handle_ending_of_context_switch(u32 pid)
{
  struct trace_event_t * obj = g_pid_to_sched_event.lookup(&pid);
  if (obj && obj->is_valid) {
    u64 now = bpf_ktime_get_ns();
    obj->dur_in_ns = now - obj->ts_in_ns;
    obj->cpu = bpf_get_smp_processor_id();

    g_trace_event_rbo.ringbuf_output(obj, sizeof(struct trace_event_t), BPF_RB_FORCE_WAKEUP);
    obj->is_valid = 0;
  }
}

TRACEPOINT_PROBE(sched, sched_switch)
{
  u32 prev_pid = args->prev_pid;
  u32 next_pid = args->next_pid;

  if (_is_cb_running(prev_pid)) {
    _handle_beginning_of_context_switch(prev_pid);
  }
  if (_is_cb_running(next_pid)) {
    _handle_ending_of_context_switch(next_pid);
  }
  return 0;
}

// clang-format off
{% for loc in cb_locs %}
int cb_in_{{loc.mangled_name}}(struct pt_regs * ctx)
// clang-format on
{
  // hook to the start of a callback function
  u64 pid_tgid = bpf_get_current_pid_tgid();
  u32 tgid = pid_tgid >> 32;
  u32 pid = pid_tgid & 0xFFFFFFFF;

  struct trace_event_t ev = {0};
  struct trace_event_t * obj = g_pid_to_trace_event.lookup_or_try_init(&pid, &ev);
  if (obj) {
    obj->tgid = tgid;
    obj->pid = pid;
    obj->ts_in_ns = bpf_ktime_get_ns();
    obj->dur_in_ns = 0;
    obj->cpu = bpf_get_smp_processor_id();
    obj->is_cb_event = 1;
    obj->is_valid = 1;
    obj->cb_index = {{loop.index0}};
  }

  return 0;
}

// clang-format off
int cb_out_{{loc.mangled_name}}(struct pt_regs * ctx)
// clang-format on
{
  // hook to the end of a callback function
  u64 pid_tgid = bpf_get_current_pid_tgid();
  u32 tgid = pid_tgid >> 32;
  u32 pid = pid_tgid & 0xFFFFFFFF;

  struct trace_event_t * obj = g_pid_to_trace_event.lookup(&pid);
  if (obj && obj->is_valid) {
    u64 now = bpf_ktime_get_ns();
    obj->dur_in_ns = now - obj->ts_in_ns;

    g_trace_event_rbo.ringbuf_output(obj, sizeof(struct trace_event_t), BPF_RB_FORCE_WAKEUP);

    // mark as invalid
    obj->cb_index = MAX_NUM_CALLBACKS;
    obj->is_valid = 0;
  }
  return 0;
}
// clang-format off
{% endfor %}
// clang-format on
