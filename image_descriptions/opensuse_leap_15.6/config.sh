#!/bin/bash
# Copyright (c) 2015 SUSE LLC
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# 
#======================================
# Functions...
#--------------------------------------
test -f /.kconfig && . /.kconfig
test -f /.profile && . /.profile

set -euxo pipefail

mkdir /var/lib/misc/reconfig_system

#======================================
# Greeting...
#--------------------------------------
echo "Configure image: [$kiwi_iname]-[$kiwi_profiles]..."

#======================================
# add missing fonts
#--------------------------------------
CONSOLE_FONT="eurlatgr.psfu"

#======================================
# prepare for setting root pw, timezone
#--------------------------------------
echo "** reset machine settings"
rm -f /etc/machine-id \
      /var/lib/zypp/AnonymousUniqueId \
      /var/lib/systemd/random-seed

echo "** Running ldconfig..."
/sbin/ldconfig

#======================================
# Setup baseproduct link
#--------------------------------------
suseSetupProduct

#======================================
# Specify default runlevel
#--------------------------------------
baseSetRunlevel 3

#======================================
# Add missing gpg keys to rpm
#--------------------------------------
suseImportBuildKey

#======================================
# Enable sshd
#--------------------------------------
chkconfig sshd on

if [ -e /etc/cloud/cloud.cfg ]; then
    systemctl enable cloud-init-local
    systemctl enable cloud-init
    systemctl enable cloud-config
    systemctl enable cloud-final
fi

# Enable jeos-firstboot
mkdir -p /var/lib/YaST2
touch /var/lib/YaST2/reconfig_system

systemctl mask systemd-firstboot.service
systemctl enable jeos-firstboot.service

# Enable firewalld if installed except on VMware
if [ -x /usr/sbin/firewalld ] && [ "$kiwi_profiles" != "VMware" ]; then
    echo 'Enabling firewall...'
    chkconfig firewalld on
fi

# Set GRUB2 to boot graphically (bsc#1097428)
sed -Ei"" "s/#?GRUB_TERMINAL=.+$/GRUB_TERMINAL=gfxterm/g" /etc/default/grub
sed -Ei"" "s/#?GRUB_GFXMODE=.+$/GRUB_GFXMODE=auto/g" /etc/default/grub

# Systemd controls the console font now
echo FONT="$CONSOLE_FONT" >> /etc/vconsole.conf

#======================================
# SSL Certificates Configuration
#--------------------------------------
echo '** Rehashing SSL Certificates...'
update-ca-certificates

if [ ! -s /var/log/zypper.log ]; then
        > /var/log/zypper.log
fi

#======================================
# Import trusted rpm keys
#--------------------------------------
for i in /usr/lib/rpm/gnupg/keys/gpg-pubkey*asc; do
    # importing can fail if it already exists
    rpm --import $i || true
done

#======================================
# Add repos from control.xml
#--------------------------------------
add-yast-repos
zypper --non-interactive rm -u live-add-yast-repos

# only for debugging
#systemctl enable debug-shell.service

#=====================================
# Configure snapper
#-------------------------------------
if [ "${kiwi_btrfs_root_is_snapper_snapshot-false}" = 'true' ]; then
        echo "creating initial snapper config ..."
        # we can't call snapper here as the .snapshots subvolume
        # already exists and snapper create-config doens't like
        # that.
        cp /etc/snapper/config-templates/default /etc/snapper/configs/root
        # Change configuration to match SLES12-SP1 values
        sed -i -e '/^TIMELINE_CREATE=/s/yes/no/' /etc/snapper/configs/root
        sed -i -e '/^NUMBER_LIMIT=/s/50/10/'     /etc/snapper/configs/root

        baseUpdateSysConfig /etc/sysconfig/snapper SNAPPER_CONFIGS root
fi

#=====================================
# Enable chrony if installed
#-------------------------------------
if [ -f /etc/chrony.conf ]; then
        suseInsertService chronyd
fi

#======================================
# Disable recommends on virtual images (keep hardware supplements, see bsc#1089498)
#--------------------------------------
sed -i 's/.*solver.onlyRequires.*/solver.onlyRequires = true/g' /etc/zypp/zypp.conf

#======================================
# Disable installing documentation
#--------------------------------------
sed -i 's/.*rpm.install.excludedocs.*/rpm.install.excludedocs = yes/g' /etc/zypp/zypp.conf

#======================================
# Configure Raspberry Pi specifics
#--------------------------------------
if [[ "$kiwi_profiles" == *"RaspberryPi"* ]]; then
        # Also show WLAN interfaces in /etc/issue
        baseUpdateSysConfig /etc/sysconfig/issue-generator NETWORK_INTERFACE_REGEX '^[bew]'

        # Add necessary kernel modules to initrd (will disappear with bsc#1084272)
        echo 'add_drivers+=" bcm2835_dma dwc2 "' > /etc/dracut.conf.d/raspberrypi_modules.conf

        # Work around network issues
        cat > /etc/modprobe.d/50-rpi3.conf <<-EOF
                # Prevent too many page allocations (bsc#1012449)
                options smsc95xx turbo_mode=N
        EOF

        cat > /usr/lib/sysctl.d/50-rpi3.conf <<-EOF
                # Avoid running out of DMA pages for smsc95xx (bsc#1012449)
                vm.min_free_kbytes = 2048
        EOF
fi

#=========================================================
# Custom Vagrant and Parallels Additions
#=========================================================

# Configure Vagrant setup if vagrant profile is active
if [ -n "${kiwi_profiles:-}" ] && [[ "$kiwi_profiles" =~ Vagrant ]]; then
    if ! getent group vagrant >/dev/null 2>&1; then
        echo "Creating vagrant group..."
        groupadd -r vagrant || groupadd vagrant
    fi
    if declare -f baseVagrantSetup >/dev/null 2>&1; then
        echo "Executing baseVagrantSetup..."
        baseVagrantSetup
    fi
fi

# Parallels Guest Tools Installation
PARALLELS_ISO_DIR="/tmp/parallels_iso"
if [ -d "$PARALLELS_ISO_DIR" ]; then
    ISO_FILE=""
    ARCH=$(uname -m)
    case "$ARCH" in
        aarch64|arm64|arm*)
            if [ -f "$PARALLELS_ISO_DIR/prl-tools-lin-arm.iso" ]; then
                ISO_FILE="$PARALLELS_ISO_DIR/prl-tools-lin-arm.iso"
            elif [ -f "$PARALLELS_ISO_DIR/prl-tools-lin.iso" ]; then
                ISO_FILE="$PARALLELS_ISO_DIR/prl-tools-lin.iso"
            fi
            ;;
        *)
            if [ -f "$PARALLELS_ISO_DIR/prl-tools-lin.iso" ]; then
                ISO_FILE="$PARALLELS_ISO_DIR/prl-tools-lin.iso"
            elif [ -f "$PARALLELS_ISO_DIR/prl-tools-lin-arm.iso" ]; then
                ISO_FILE="$PARALLELS_ISO_DIR/prl-tools-lin-arm.iso"
            fi
            ;;
    esac

    if [ -z "$ISO_FILE" ]; then
        ISO_FILE=$(find "$PARALLELS_ISO_DIR" -maxdepth 1 -name "*.iso" 2>/dev/null | head -n 1 || true)
    fi

    if [ -n "$ISO_FILE" ] && [ -f "$ISO_FILE" ]; then
        echo "Found Parallels Tools ISO: $ISO_FILE"
        MNT_DIR="/tmp/parallels_mnt"
        mkdir -p "$MNT_DIR"

        # Ensure compatibility symlinks for legacy Parallels service installer
        if [ ! -x /sbin/insserv ]; then
            if [ -x /usr/sbin/insserv ]; then
                ln -sf /usr/sbin/insserv /sbin/insserv
            else
                ln -sf /bin/true /sbin/insserv
            fi
        fi

        echo "Mounting $ISO_FILE..."
        if mount -o loop "$ISO_FILE" "$MNT_DIR"; then
            if [ -x "$MNT_DIR/install" ]; then
                echo "Installing Parallels Guest Tools..."
                if ! "$MNT_DIR/install" --install-unattended --verbose; then
                    code=$?
                    echo "Parallels tools installer exited with status $code"

                    echo "=== [DIAGNOSTIC] Installed Kernel & Compiler Packages ==="
                    rpm -q gcc make dkms kernel-default kernel-default-devel kernel-macros perl bc || true

                    echo "=== [DIAGNOSTIC] Directory structures for kernel source ==="
                    ls -la /lib/modules/ || true
                    ls -la /usr/src/linux/ || true

                    for logfile in /var/log/parallels-tools-install.log /var/log/parallels-installer.log; do
                        if [ -f "$logfile" ]; then
                            echo "=== $logfile ==="
                            cat "$logfile"
                        fi
                    done
                fi
            fi
            umount "$MNT_DIR" || true
        fi
        rm -rf "$MNT_DIR" "$PARALLELS_ISO_DIR"
    else
        echo "No Parallels Guest Tools ISO found in $PARALLELS_ISO_DIR. Skipping Parallels Tools installation."
    fi
else
    echo "Parallels ISO directory not mounted. Skipping Parallels Tools installation."
fi

exit 0
