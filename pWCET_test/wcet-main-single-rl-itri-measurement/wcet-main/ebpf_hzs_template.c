#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

{% for demangled_name, loc in cb_locs.items() %}

BPF_ARRAY(g_first_probing_time_ns_{{loc.mangled_name}}, u64, 1);
BPF_ARRAY(g_last_probing_time_ns_{{loc.mangled_name}}, u64, 1);
BPF_ARRAY(g_num_probing_{{loc.mangled_name}}, s32, 1);

static void set_first_probing_time_ns_if_needed_{{loc.mangled_name}}(u64 timestamp)
{
  s32 zero = 0;
  u64 *val = g_first_probing_time_ns_{{loc.mangled_name}}.lookup(&zero);
  if (val && *val == 0) {
    *val = timestamp;
  }
}

int cb_in_{{loc.mangled_name}}(struct pt_regs *ctx) {
  // hook to the start of a callback function
  s32 zero = 0;
  u64 now = bpf_ktime_get_ns();
  set_first_probing_time_ns_if_needed_{{loc.mangled_name}}(now);
  g_num_probing_{{loc.mangled_name}}.increment(zero);

  g_last_probing_time_ns_{{loc.mangled_name}}.update(&zero, &now);
  return 0;
}

{% endfor %}
