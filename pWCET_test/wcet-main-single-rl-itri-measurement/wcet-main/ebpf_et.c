#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

#define MAX_NUM_SAMPLES 3000
/*
Maintain two arrays for measuring execution time of a callback function:
Index                        0         1         2       ...
g_response_times_ns        456         789       1025
g_acc_syscall_times_ns     100         300        250
-----------------------------------------------------------
exec_times_ns              356         489        775

exec_times_ns is calculated by top-level Python program. It is not in the
eBPF.
*/

// Each sampled response time is stored in g_response_times_ns.
// When BPF_ARRAY is full, stop sampling.
BPF_ARRAY(g_response_times_ns, u64, MAX_NUM_SAMPLES);
BPF_ARRAY(g_acc_syscall_times_ns, u64, MAX_NUM_SAMPLES);
BPF_ARRAY(g_num_samples, s32, 1);

// The same callback can be called on different processes,
// so use a hash table to memorize the start time for each call.
// Define g_cb_start_time_dict[pid_gtid] = 0 when the callback is not
// invoked.
BPF_HASH(g_cb_start_time_dict, u64, u64);  // pid_tgid -> timestamp

// During the execution of the callback, it can invoke syscalls multiple times.
// We need to accumulate the time spent in syscalls.
BPF_HASH(g_syscall_start_time_dict, u64, u64);  // pid_tgid -> timestamp
BPF_HASH(g_acc_syscall_time_dict, u64, u64);  // pid_tgid -> accumulated syscall time

static s32 get_sampling_index() {
  s32 zero = 0;
  s32 *val = g_num_samples.lookup(&zero);
  if (val) {
    return *val;
  }
  return MAX_NUM_SAMPLES;
}

static u64 get_acc_syscall_time(u64 pid_tgid) {
  u64 *acc_time = g_acc_syscall_time_dict.lookup(&pid_tgid);
  if (acc_time) {
    return *acc_time;
  } else {
    return 0;
  }
}

static void accumulate_syscall_time(u64 pid_tgid, u64 duration_ns) {
  u64 zero = 0;
  u64 *acc_time = g_acc_syscall_time_dict.lookup_or_try_init(&pid_tgid, &zero);
  if (acc_time) {
    *acc_time += duration_ns;
  }
}

static u64 calc_this_syscall_duration(u64 pid_tgid) {
  u64 *start = g_syscall_start_time_dict.lookup(&pid_tgid);
  if (start && (*start > 0)) {
    u64 duration_ns = bpf_ktime_get_ns() - *start;
    *start = 0;
    return duration_ns;
  }
  return 0;
}

static u64 calc_this_response_duration(u64 pid_tgid) {
  u64 *start = g_cb_start_time_dict.lookup(&pid_tgid);
  if (start && (*start > 0)) {
    u64 duration_ns = bpf_ktime_get_ns() - *start;
    *start = 0;
    return duration_ns;
  }
  return 0;
}

static void log_syscall_start_time(u64 pid_tgid) {
  u64 now = bpf_ktime_get_ns();
  g_syscall_start_time_dict.update(&pid_tgid, &now);
}

static int should_accumulate_syscall_time(u64 pid_tgid) {
  s32 sidx = get_sampling_index();
  if (sidx == MAX_NUM_SAMPLES) {
    return 0;
  }

  u64 *start_time = g_cb_start_time_dict.lookup(&pid_tgid);
  if (start_time && (*start_time > 0)) {
    return 1;
  } else {
    return 0;
  }
}

static void start_accumulate_syscall_time(u64 pid_tgid) {
  u64 now = bpf_ktime_get_ns();
  g_cb_start_time_dict.update(&pid_tgid, &now);
}

static void stop_accumulate_syscall_time(u64 pid_tgid) {
  u64 zero = 0;
  g_cb_start_time_dict.update(&pid_tgid, &zero);  // mark the exit of the function
  g_acc_syscall_time_dict.update(&pid_tgid, &zero);
}

int cb_in(struct pt_regs *ctx) {
  // hook to the start of a callback function
  s32 sidx = get_sampling_index();
  if (sidx < MAX_NUM_SAMPLES) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    start_accumulate_syscall_time(pid_tgid);
  }
  return 0;
}

int cb_out(struct pt_regs *ctx) {
  s32 sidx = get_sampling_index();
  if (sidx < MAX_NUM_SAMPLES) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u64 resp_duration_ns = calc_this_response_duration(pid_tgid);
    u64 acc_syscall_duration_ns = get_acc_syscall_time(pid_tgid);

    g_response_times_ns.update(&sidx, &resp_duration_ns);
    g_acc_syscall_times_ns.update(&sidx, &acc_syscall_duration_ns);

    stop_accumulate_syscall_time(pid_tgid);
    g_num_samples.increment(0);
  }
  return 0;
}

int syscall_in(struct pt_regs *ctx) {
  u64 pid_tgid = bpf_get_current_pid_tgid();
  if (should_accumulate_syscall_time(pid_tgid)) {
    log_syscall_start_time(pid_tgid);
  }
  return 0;
};

int syscall_out(struct pt_regs *ctx) {
  u64 pid_tgid = bpf_get_current_pid_tgid();

  if (should_accumulate_syscall_time(pid_tgid)) {
    u64 duration_ns = calc_this_syscall_duration(pid_tgid);
    accumulate_syscall_time(pid_tgid, duration_ns);
  }

  return 0;
}
