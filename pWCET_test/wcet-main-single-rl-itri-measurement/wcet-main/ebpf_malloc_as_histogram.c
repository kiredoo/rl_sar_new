#include <linux/mm_types.h>
#include <linux/sched.h>
#include <uapi/linux/ptrace.h>

#define MAX_BIT_LEN 64

struct histogram_t {
  s32 bit_len_count[MAX_BIT_LEN + 1];
  u64 total_allocated_bytes;
};

BPF_RINGBUF_OUTPUT(g_histogram_rbo, 1);         // 1 page
BPF_ARRAY(g_histogram, struct histogram_t, 1);  // 1 element
BPF_HASH(g_is_cb_active, u64, s32);             // pid_tgid -> True/False

static s32 _bit_len(u64 val) {
  // Return the bit-width of the significant part of the value
  // 00000000 00000000 00000000 00010110 -> return 5
  // 00000000 00000000 00000000 00000000 -> return 0
  // 10000000 00100000 00000111 00000000 -> return 32

  // use binary search to find the bit length
  s32 left = 0, right = 63;
  while (left <= right) {
    s32 mid = (left + right) >> 1;
    u64 shift_result = val >> mid;
    if (shift_result > 0) {
      left = mid + 1;
    } else {
      right = mid - 1;
    }
  }
  return left;
}

int malloc_in(struct pt_regs *ctx) {
  // hook to the start of a callback function
  u64 pid_tgid = bpf_get_current_pid_tgid();
  s32 *is_active = g_is_cb_active.lookup(&pid_tgid);

  if (is_active && (*is_active)) {
    s32 zero = 0;
    struct histogram_t *histogram = g_histogram.lookup(&zero);
    if (histogram) {
      u64 allocated_bytes = PT_REGS_PARM1(ctx);
      s32 len = _bit_len(allocated_bytes);
      histogram->bit_len_count[len] += 1;
      histogram->total_allocated_bytes += allocated_bytes;
    }
  }

  return 0;
}

int cb_in(struct pt_regs *ctx) {
  // hook to the start of a callback function
  s32 zero = 0;
  s32 active = 1;
  u64 pid_tgid = bpf_get_current_pid_tgid();
  g_is_cb_active.update(&pid_tgid, &active);

  struct histogram_t *histogram = g_histogram.lookup(&zero);
  if (histogram) {
    for (s32 i = 0; i <= MAX_BIT_LEN; i++) {
      histogram->bit_len_count[i] = 0;
    }
    histogram->total_allocated_bytes = 0;
  }
  return 0;
}

int cb_out(struct pt_regs *ctx) {
  // hook to the end of a callback function
  s32 zero = 0;
  s32 active = 0;
  u64 pid_tgid = bpf_get_current_pid_tgid();
  g_is_cb_active.update(&pid_tgid, &active);

  struct histogram_t *histogram = g_histogram.lookup(&zero);
  if (histogram) {
    g_histogram_rbo.ringbuf_output(histogram, sizeof(struct histogram_t),
                                   BPF_RB_FORCE_WAKEUP);
  }

  return 0;
}
