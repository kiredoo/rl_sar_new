#include <linux/mm_types.h>
#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

#define MALLOC_INDEX 0
#define FREE_INDEX 1

struct call_t {
  u64 arg;
  u64 ret;
  u64 pid_tgid;
  s32 is_malloc;
};

BPF_RINGBUF_OUTPUT(g_call_rbo, 1);    // 1 page
BPF_HASH(g_call, u64, struct call_t);  // pid_tgid: struct call_t
BPF_HASH(g_is_cb_active, u64, s32);   // pid_tgid -> True/False

int malloc_in(struct pt_regs *ctx) {
  u64 pid_tgid = bpf_get_current_pid_tgid();
  s32 *is_active = g_is_cb_active.lookup(&pid_tgid);

  if (is_active && (*is_active)) {
    struct call_t init_call = {0};
    struct call_t *call = g_call.lookup_or_try_init(&pid_tgid, &init_call);
    if (call) {
      call->is_malloc = 1;
      call->arg = PT_REGS_PARM1(ctx);
      call->ret = 0;
      call->pid_tgid = pid_tgid;
    }
  }
  return 0;
}

int malloc_out(struct pt_regs *ctx) {
  u64 pid_tgid = bpf_get_current_pid_tgid();
  s32 *is_active = g_is_cb_active.lookup(&pid_tgid);

  if (is_active && (*is_active)) {
    struct call_t *call = g_call.lookup(&pid_tgid);
    if (call) {
      call->ret = PT_REGS_RC(ctx);
      g_call_rbo.ringbuf_output(call, sizeof(struct call_t),
                                BPF_RB_FORCE_WAKEUP);
    }
  }
  return 0;
}

int free_in(struct pt_regs *ctx) {
  u64 pid_tgid = bpf_get_current_pid_tgid();
  s32 *is_active = g_is_cb_active.lookup(&pid_tgid);

  if (is_active && (*is_active)) {
    struct call_t call = {0};
    call.arg = PT_REGS_PARM1(ctx);
    call.ret = 0;
    call.is_malloc = 0;
    call.pid_tgid = pid_tgid;

    g_call_rbo.ringbuf_output(&call, sizeof(struct call_t),
                              BPF_RB_FORCE_WAKEUP);
  }
  return 0;
}

int cb_in(struct pt_regs *ctx) {
  // hook to the start of a callback function
  s32 active = 1;
  u64 pid_tgid = bpf_get_current_pid_tgid();
  g_is_cb_active.update(&pid_tgid, &active);
  return 0;
}

int cb_out(struct pt_regs *ctx) {
  // hook to the end of a callback function
  s32 active = 0;
  u64 pid_tgid = bpf_get_current_pid_tgid();
  g_is_cb_active.update(&pid_tgid, &active);

  struct call_t call = {0};
  g_call_rbo.ringbuf_output(&call, sizeof(struct call_t), BPF_RB_FORCE_WAKEUP);
  return 0;
}
