#!/bin/bash
# Check CUPS printer logs for errors

echo "========================================="
echo "CUPS Error Log (last 50 lines)"
echo "========================================="
sudo tail -n 50 /var/log/cups/error_log

echo ""
echo "========================================="
echo "CUPS Access Log (last 20 lines)"
echo "========================================="
sudo tail -n 20 /var/log/cups/access_log

echo ""
echo "========================================="
echo "CUPS Page Log (last 20 lines)"
echo "========================================="
sudo tail -n 20 /var/log/cups/page_log

echo ""
echo "========================================="
echo "Current Print Queue Status"
echo "========================================="
lpstat -t

echo ""
echo "========================================="
echo "Recent Failed Jobs"
echo "========================================="
lpstat -W completed | tail -n 10

echo ""
echo "========================================="
echo "Check specific job (if you have job ID)"
echo "========================================="
echo "Run: lpstat -l -W completed | grep <job-id> -A 10"
