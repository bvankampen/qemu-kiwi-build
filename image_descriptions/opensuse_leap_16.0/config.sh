#!/bin/bash
# config.sh - Image customization script executed inside target chroot during KIWI build.

set -euo pipefail

# Base KIWI helper functions
test -f /.kconfig && . /.kconfig
test -f /.profile && . /.profile

echo "Running post-install configuration script (config.sh)..."

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
