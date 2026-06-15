/*
Jinja2 template that generate eBPF code in C syntax.

Input:
cb_locs: {demangle_name: FuncLocation}, where a FuncLocation is a dataclass. For example:
  FuncLocation(index=0, demangled_name='itri::YOLOv10Node::image_cb', mangled_name='_ZN4itri11YOLOv10Node8image_cbESt10shared_ptrIN11sensor_msgs3msg6Image_ISaIvEEEE', fullpath='/home/chtseng18/repo/itriadv_l2/install/yolov10_ros2/lib/libyolov10_ros2.so')

num_cb: the length of |cb_locs|. We pass it to Jinja2 template because len(cb_locs) is not allowed.
*/
#include <linux/mm_types.h>
#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

#define NUM_CB {{num_cb}}  // number of callback functions

struct mm_fault_stat_t {
  u64 num_cb_called;
  u64 num_major_faults;
  u64 num_minor_faults;
  u64 handle_mm_fault_time_ns;
};


// each callback maps to an entry in |g_mm_faults_table|, indexed by cb_loc.index
BPF_ARRAY(g_mm_faults_table, struct mm_fault_stat_t, NUM_CB);

// Map a callback's pid_tgid to its (internal) index given in FuncLocation so that
// we can quickly find the corresponding entry in |g_mm_faults_table|.
// If a callback function is not active (that is, not executed), the mapped index is NUM_CB
// and we don't update the table entry.
BPF_HASH(g_cb_pid_tgid_to_mm_faults_table_index, u64, s32);

// The start time of handle_mm_fault.
BPF_ARRAY(g_handle_mm_fault_start_time_ns, u64, NUM_CB);

int handle_mm_fault_in(struct pt_regs *ctx) {
  u64 pid_tgid = bpf_get_current_pid_tgid();
  s32 *cb_index = g_cb_pid_tgid_to_mm_faults_table_index.lookup(&pid_tgid);
  if ((!cb_index) || (*cb_index >= NUM_CB)) {
    return 0;
  }

  u64 now = bpf_ktime_get_ns();
  g_handle_mm_fault_start_time_ns.update(cb_index, &now);

  struct mm_fault_stat_t *fault_data = g_mm_faults_table.lookup(cb_index);

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
  u64 pid_tgid = bpf_get_current_pid_tgid();
  s32 *cb_index = g_cb_pid_tgid_to_mm_faults_table_index.lookup(&pid_tgid);
  if ((!cb_index) || (*cb_index >= NUM_CB)) {
    return 0;
  }

  u64 handle_mm_fault_time_ns = 0;
  u64 *start_time = g_handle_mm_fault_start_time_ns.lookup(cb_index);
  if (start_time && *start_time > 0) {
    handle_mm_fault_time_ns = bpf_ktime_get_ns() - *start_time;
    *start_time = 0;
  }

  struct mm_fault_stat_t *fault_data = g_mm_faults_table.lookup(cb_index);

  if (fault_data) {
    fault_data->handle_mm_fault_time_ns += handle_mm_fault_time_ns;
  }
  return 0;
}


{% for demangled_name, loc in cb_locs.items() %}
int cb_in_{{loc.mangled_name}}(struct pt_regs *ctx) {
  // hook to the start of {{demangled_name}}
  s32 cb_index = {{loc.index}};
  u64 pid_tgid = bpf_get_current_pid_tgid();
  g_cb_pid_tgid_to_mm_faults_table_index.update(&pid_tgid, &cb_index);

  struct mm_fault_stat_t *fault_data = g_mm_faults_table.lookup(&cb_index);
  if (fault_data) {
    fault_data->num_cb_called += 1;
  }
  return 0;
}

int cb_out_{{loc.mangled_name}}(struct pt_regs *ctx) {
  // hook to the end of {{demangled_name}}
  u64 pid_tgid = bpf_get_current_pid_tgid();
  s32 invalid_index = NUM_CB;
  g_cb_pid_tgid_to_mm_faults_table_index.update(&pid_tgid, &invalid_index);
  return 0;
}
{% endfor %}
