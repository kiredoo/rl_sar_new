#include <linux/mm_types.h>
#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

struct mm_fault_stat_t {
  u64 num_cb_called;
  u64 num_major_faults;
  u64 num_minor_faults;
  u64 handle_mm_fault_time_ns;
};

BPF_ARRAY(g_mm_faults_table, struct mm_fault_stat_t, 1);
BPF_ARRAY(g_cb_pid_tgid, u64, 1);
BPF_HASH(g_handle_mm_fault_start_time_ns, u64, u64);

int handle_mm_fault_in(struct pt_regs *ctx) {
  s32 zero = 0;
  u64 *cb_pid_tgid = g_cb_pid_tgid.lookup(&zero);
  u64 pid_tgid = bpf_get_current_pid_tgid();
  if (cb_pid_tgid && (*cb_pid_tgid != pid_tgid)) {
    return 0;
  }

  u64 now = bpf_ktime_get_ns();
  g_handle_mm_fault_start_time_ns.update(&pid_tgid, &now);

  struct mm_fault_stat_t *fault_data = g_mm_faults_table.lookup(&zero);

  int fault_type = PT_REGS_RC(ctx);
  if (fault_data) {
    if (fault_type == VM_FAULT_MAJOR) {
      fault_data->num_major_faults += 1;
    } else {
      fault_data->num_minor_faults += 1;
    }
  }
  return 0;
}


int handle_mm_fault_out(struct pt_regs *ctx) {
  s32 zero = 0;
  u64 *cb_pid_tgid = g_cb_pid_tgid.lookup(&zero);
  u64 pid_tgid = bpf_get_current_pid_tgid();
  if (cb_pid_tgid && (*cb_pid_tgid != pid_tgid)) {
    return 0;
  }

  u64 handle_mm_fault_time_ns = 0;
  u64 *start_time = g_handle_mm_fault_start_time_ns.lookup(&pid_tgid);
  if (start_time && *start_time > 0) {
    handle_mm_fault_time_ns = bpf_ktime_get_ns() - *start_time;
    *start_time = 0;
  }

  struct mm_fault_stat_t *fault_data = g_mm_faults_table.lookup(&zero);

  if (fault_data) {
    fault_data->handle_mm_fault_time_ns += handle_mm_fault_time_ns;
  }
  return 0;
}



int cb_in(struct pt_regs *ctx) {
  // hook to the start of a callback function
  s32 zero = 0;
  u64 pid_tgid = bpf_get_current_pid_tgid();
  g_cb_pid_tgid.update(&zero, &pid_tgid);

  struct mm_fault_stat_t *fault_data = g_mm_faults_table.lookup(&zero);
  if (fault_data) {
    fault_data->num_cb_called += 1;
  }
  return 0;
}

int cb_out(struct pt_regs *ctx) {
  // hook to the end of a callback function
  s32 zero = 0;
  u64 u64zero = 0;
  g_cb_pid_tgid.update(&zero, &u64zero);
  return 0;
}
