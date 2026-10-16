/*
 * Userspace regression test for the strixec read/write loops.
 * The two I/O functions are extracted verbatim from ../strixec.c by run.sh
 * (into io_under_test.inc); kernel primitives are stubbed here.
 */
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>

typedef unsigned char u8;
#define __user
#define EC_SPACE_SIZE 256
struct file { int dummy; };

static u8 ec[256];
static int ops, ec_fail_at = -1;          /* index of the EC access that fails */
static const char *fault_ptr;             /* user pointer that faults */

static int ec_read(u8 off, u8 *v)  { if (ops++ == ec_fail_at) return -5; *v = ec[off]; return 0; }
static int ec_write(u8 off, u8 v)  { if (ops++ == ec_fail_at) return -5; ec[off] = v; return 0; }
#define put_user(x, p) ((p) == fault_ptr ? -EFAULT : ((*(p)) = (char)(x), 0))
#define get_user(x, p) ((p) == fault_ptr ? -EFAULT : ((x) = (u8)*(p), 0))

#include "io_under_test.inc"

static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("  FAIL: " __VA_ARGS__); printf("\n"); } } while (0)

static void reset(void) { memset(ec, 0, sizeof(ec)); ops = 0; ec_fail_at = -1; fault_ptr = NULL; }

/* Write 3 bytes at 0x10; the second EC write fails. The caller retries the rest
 * at the file position it was given back, as a buffered writer does. */
static void test_write_partial_ec_error(void)
{
	struct file f; loff_t pos = 0x10; char buf[3] = {0x1A, 0x1B, 0x1C}; ssize_t n;
	reset(); ec_fail_at = 1;
	n = strixec_write(&f, buf, 3, &pos);
	CHECK(n == 1, "write short count: got %zd want 1", n);
	CHECK(pos == 0x11, "write ppos after short write: got 0x%02llx want 0x11", (long long)pos);
	ec_fail_at = -1;
	n = strixec_write(&f, buf + 1, 2, &pos);
	CHECK(n == 2, "write retry count: got %zd want 2", n);
	CHECK(ec[0x10] == 0x1A && ec[0x11] == 0x1B && ec[0x12] == 0x1C,
	      "write retry bytes: EC 10..12 = %02X %02X %02X", ec[0x10], ec[0x11], ec[0x12]);
}

static void test_read_partial_ec_error(void)
{
	struct file f; loff_t pos = 0x20; char out[3] = {0}; ssize_t n;
	reset(); ec[0x20] = 0xA0; ec[0x21] = 0xA1; ec[0x22] = 0xA2; ec_fail_at = 1;
	n = strixec_read(&f, out, 3, &pos);
	CHECK(n == 1, "read short count: got %zd want 1", n);
	CHECK(pos == 0x21, "read ppos after short read: got 0x%02llx want 0x21", (long long)pos);
	ec_fail_at = -1;
	n = strixec_read(&f, out + 1, 2, &pos);
	CHECK(n == 2 && out[0] == (char)0xA0 && out[1] == (char)0xA1 && out[2] == (char)0xA2,
	      "read retry data: n=%zd bytes %02X %02X %02X", n,
	      (u8)out[0], (u8)out[1], (u8)out[2]);
}

/* A user fault after one byte was already transferred must report the progress,
 * not -EFAULT, and must not move ppos past the byte that was not copied. */
static void test_write_fault_after_progress(void)
{
	struct file f; loff_t pos = 0x30; char buf[2] = {0x3A, 0x3B}; ssize_t n;
	reset(); fault_ptr = &buf[1];
	n = strixec_write(&f, buf, 2, &pos);
	CHECK(n == 1, "write fault short count: got %zd want 1", n);
	CHECK(pos == 0x31, "write fault ppos: got 0x%02llx want 0x31", (long long)pos);
	CHECK(ec[0x30] == 0x3A, "write fault first byte: EC 30 = %02X", ec[0x30]);
}

static void test_read_fault_after_progress(void)
{
	struct file f; loff_t pos = 0x40; char out[2] = {0}; ssize_t n;
	reset(); ec[0x40] = 0x4A; ec[0x41] = 0x4B; fault_ptr = &out[1];
	n = strixec_read(&f, out, 2, &pos);
	CHECK(n == 1, "read fault short count: got %zd want 1", n);
	CHECK(pos == 0x41, "read fault ppos: got 0x%02llx want 0x41", (long long)pos);
}

static void test_full_transfer(void)
{
	struct file f; loff_t pos = 0x50; char buf[4] = {1, 2, 3, 4}; char out[4] = {0}; ssize_t n;
	reset();
	n = strixec_write(&f, buf, 4, &pos);
	CHECK(n == 4 && pos == 0x54, "full write: n=%zd pos=0x%02llx", n, (long long)pos);
	pos = 0x50;
	n = strixec_read(&f, out, 4, &pos);
	CHECK(n == 4 && pos == 0x54 && memcmp(out, buf, 4) == 0, "full read round-trip");
}

static void test_error_with_no_progress(void)
{
	struct file f; loff_t pos = 0x60; char buf[1] = {9}; ssize_t n;
	reset(); ec_fail_at = 0;
	n = strixec_write(&f, buf, 1, &pos);
	CHECK(n == -EIO && pos == 0x60, "write no progress: n=%zd pos=0x%02llx", n, (long long)pos);
}

int main(void)
{
	test_write_partial_ec_error();
	test_read_partial_ec_error();
	test_write_fault_after_progress();
	test_read_fault_after_progress();
	test_full_transfer();
	test_error_with_no_progress();
	if (failures) { printf("%d check(s) failed\n", failures); return 1; }
	printf("all io loop checks passed\n");
	return 0;
}
