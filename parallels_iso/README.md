# Parallels Guest Tools ISO Directory

Place the Parallels Tools installer ISO image in this folder prior to building with the `Vagrant-parallels` profile or running `build-image.sh --with-parallels`:

- `prl-tools-lin.iso` for `x86_64`
- `prl-tools-lin-arm.iso` for `aarch64`

When building the `Vagrant-parallels` image, the script will automatically mount this directory into the build container and run the unattended Parallels Guest Tools installer.

---

## Default ISO Locations in Parallels Desktop

### On macOS (Mac)
If Parallels Desktop is installed on macOS, you can find and copy the ISOs directly from the Parallels application bundle:

- **ARM64 (Apple Silicon M1/M2/M3):**
  `/Applications/Parallels Desktop.app/Contents/Resources/Tools/prl-tools-lin-arm.iso`
- **x86_64 (Intel Mac):**
  `/Applications/Parallels Desktop.app/Contents/Resources/Tools/prl-tools-lin.iso`

**Example copy commands on Mac:**
```bash
# For Apple Silicon (ARM64):
cp "/Applications/Parallels Desktop.app/Contents/Resources/Tools/prl-tools-lin-arm.iso" ./parallels_iso/

# For Intel (x86_64):
cp "/Applications/Parallels Desktop.app/Contents/Resources/Tools/prl-tools-lin.iso" ./parallels_iso/
```

### On Windows (PC)
If Parallels Desktop or Parallels Workstation is installed on Windows:

- `C:\Program Files\Parallels\Parallels Desktop\Tools\prl-tools-lin.iso`
- `C:\Program Files (x86)\Parallels\Parallels Desktop\Tools\prl-tools-lin.iso`

### On Linux (PC)
If Parallels Server or Desktop for Linux is installed:

- `/usr/share/parallels-desktop/tools/prl-tools-lin.iso`
- `/usr/lib/parallels-desktop/tools/prl-tools-lin.iso`
