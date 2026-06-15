#include <linux/mm_types.h>
#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

struct malloc_size_count {
  u64 size;
  u64 count;
};

#define MAX_EXPLICIT_SIZE 1024

// [0..MAX_EXPLICIT_SIZE]: exact count for each allocation size
// MAX_EXPLICIT_SIZE +1 :  count for all allocation size > MAX_EXPLICIT_SIZE
BPF_ARRAY(g_malloc_size_count, struct malloc_size_count, MAX_EXPLICIT_SIZE + 2);

int malloc_in(struct pt_regs *ctx) {
  u64 pid_tgid = bpf_get_current_pid_tgid();
  u32 tgid = pid_tgid >> 32; // same as getpid() in user space

  if (
{% for ros2_pid in ros2_pids %}
  tgid == {{ ros2_pid }} ||
{% endfor %}
  0)
  {
    u64 size = PT_REGS_PARM1(ctx);
    s32 index = size;
    if (size > MAX_EXPLICIT_SIZE)
    {
      index = MAX_EXPLICIT_SIZE + 1;
    }
    struct malloc_size_count *ptr = g_malloc_size_count.lookup(&index);
    if (ptr) {
      ptr->size = size;
      ptr->count += 1;
    }
  }
  return 0;
}
