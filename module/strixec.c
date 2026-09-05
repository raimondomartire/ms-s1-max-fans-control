// SPDX-License-Identifier: GPL-2.0
/*
 * strixec - EC register I/O for kernels built WITHOUT CONFIG_ACPI_EC_DEBUGFS
 * (Fedora) AND running under Secure Boot kernel lockdown (which forbids the
 * debugfs interface used by the stock ec_sys / strix-halo-fand).
 *
 * Exposes a misc char device /dev/strixec (root-only, 0600). Byte at file
 * offset O maps to EC register O via the EXPORTED kernel API ec_read()/
 * ec_write(). Seek + read/write, exactly like /sys/kernel/debug/ec/ec0/io,
 * but NOT gated by LOCKDOWN_DEBUGFS.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/miscdevice.h>
#include <linux/acpi.h>
#include <linux/uaccess.h>
#include <linux/fs.h>

#define EC_SPACE_SIZE 256

static ssize_t strixec_read(struct file *f, char __user *ubuf,
			    size_t count, loff_t *ppos)
{
	loff_t pos = *ppos;
	size_t i = 0;
	u8 val;

	if (pos < 0 || pos >= EC_SPACE_SIZE)
		return 0;

	while (i < count && pos < EC_SPACE_SIZE) {
		if (ec_read((u8)pos, &val))
			return i ? (ssize_t)i : -EIO;
		if (put_user(val, ubuf + i))
			return -EFAULT;
		i++;
		pos++;
	}
	*ppos = pos;
	return i;
}

static ssize_t strixec_write(struct file *f, const char __user *ubuf,
			     size_t count, loff_t *ppos)
{
	loff_t pos = *ppos;
	size_t i = 0;
	u8 val;

	if (pos < 0 || pos >= EC_SPACE_SIZE)
		return -EINVAL;

	while (i < count && pos < EC_SPACE_SIZE) {
		if (get_user(val, ubuf + i))
			return -EFAULT;
		if (ec_write((u8)pos, val))
			return i ? (ssize_t)i : -EIO;
		i++;
		pos++;
	}
	*ppos = pos;
	return i;
}

static const struct file_operations strixec_fops = {
	.owner   = THIS_MODULE,
	.llseek  = default_llseek,
	.read    = strixec_read,
	.write   = strixec_write,
};

static struct miscdevice strixec_dev = {
	.minor = MISC_DYNAMIC_MINOR,
	.name  = "strixec",
	.fops  = &strixec_fops,
	.mode  = 0600,
};

static int __init strixec_init(void)
{
	int ret = misc_register(&strixec_dev);

	if (ret)
		pr_err("strixec: misc_register failed: %d\n", ret);
	else
		pr_info("strixec: /dev/strixec ready (via ec_read/ec_write)\n");
	return ret;
}

static void __exit strixec_exit(void)
{
	misc_deregister(&strixec_dev);
	pr_info("strixec: unloaded\n");
}

module_init(strixec_init);
module_exit(strixec_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("adapted for Minisforum MS-S1 MAX");
MODULE_DESCRIPTION("EC register I/O via /dev/strixec using exported ec_read/ec_write");
