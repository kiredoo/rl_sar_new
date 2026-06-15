#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

/*
Maintain three variables to measure the HZ of a callback function
  - first_probing_time_ns: The time of the first probing.
  - last_probing_time_ns: The time of the last probing
  - num_probings: the number of probings.
  duration_sec = (last_probing_time_ns - first_probing_time_ns) / 1e9
  HZ = (num_probings - 1) / duration_sec.
  Both duration_sec and HZ are calculated in the python frontend.
*/

BPF_ARRAY(g_first_probing_time_ns, u64, 1);
BPF_ARRAY(g_last_probing_time_ns, u64, 1);
BPF_ARRAY(g_num_probing, s32, 1);

static void set_first_probing_time_ns_if_needed(u64 timestamp)
{
  s32 zero = 0;
  u64 *val = g_first_probing_time_ns.lookup(&zero);
  if (val && *val == 0) {
    *val = timestamp;
  }
}

int cb_in(struct pt_regs *ctx) {
  // hook to the start of a callback function
  s32 zero = 0;
  u64 now = bpf_ktime_get_ns();
  set_first_probing_time_ns_if_needed(now);
  g_num_probing.increment(zero);

  g_last_probing_time_ns.update(&zero, &now);
  return 0;
}
