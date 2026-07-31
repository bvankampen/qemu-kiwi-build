#!/usr/bin/env python3
# kiwi-build.py - Run the KIWI box build VM natively with QEMU on Linux and macOS.
# This script boots the VM and runs the KIWI build natively over SSH using paramiko for real-time, unbuffered logs.

import os
import sys
import subprocess

# Determine virtual environment paths
script_dir = os.path.dirname(os.path.abspath(__file__))
venv_dir = os.path.join(script_dir, '.venv')
venv_python = os.path.join(venv_dir, 'bin', 'python3')

# 1. If .venv doesn't exist, create it and install paramiko!
if not os.path.exists(venv_dir):
    print("Virtual environment ('.venv') not found. Bootstrapping local python environment...")
    try:
        # Create virtual environment
        subprocess.run([sys.executable, '-m', 'venv', venv_dir], check=True)
        # Install paramiko
        venv_pip = os.path.join(venv_dir, 'bin', 'pip')
        print("Installing required python dependencies ('paramiko')...")
        subprocess.run([venv_pip, 'install', '--quiet', 'paramiko'], check=True)
        print("Bootstrap complete!\n")
    except Exception as e:
        print(f"Error: Failed to bootstrap python virtual environment: {e}")
        sys.exit(1)

# 2. Auto-re-execute inside .venv if we are not already inside it
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

# 3. Handle missing dependencies dynamically inside the virtual environment
try:
    import paramiko
except ModuleNotFoundError:
    if sys.executable == venv_python:
        print("Required python dependency ('paramiko') is missing. Installing...")
        try:
            venv_pip = os.path.join(venv_dir, 'bin', 'pip')
            subprocess.run([venv_pip, 'install', '--quiet', 'paramiko'], check=True)
            import paramiko
        except Exception as e:
            print(f"Error: Failed to install 'paramiko': {e}")
            sys.exit(1)
    else:
        print("Error: Required python dependency ('paramiko') is missing.")
        sys.exit(1)

import platform
import shutil
import argparse
import urllib.request
import tarfile
import struct
import ctypes
import datetime
import socket
import time

# Pre-defined box configurations from kiwi-boxed-plugin configuration
BOX_CONFIGS = {
    'leap': {
        'x86_64': {
            'repo': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/SelfContained:/leap/images/',
            'system_file': 'Leap-Box.x86_64-System.qcow2',
            'kernel_tar': 'Leap-Box.x86_64-Kernel.tar.xz',
            'cmdline': 'root=/dev/vda1 rd.plymouth=0',
            'use_initrd': True
        }
    },
    'tumbleweed': {
        'x86_64': {
            'repo': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/SelfContained:/tumbleweed/images/',
            'system_file': 'TumbleWeed-Box.x86_64-System.qcow2',
            'kernel_tar': 'TumbleWeed-Box.x86_64-Kernel.tar.xz',
            'cmdline': 'root=/dev/vda3 rd.plymouth=0',
            'use_initrd': True
        },
        'aarch64': {
            'repo': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/SelfContained:/tumbleweed/images/',
            'system_file': 'TumbleWeed-Box.aarch64-System.qcow2',
            'kernel_tar': 'TumbleWeed-Box.aarch64-Kernel.tar.xz',
            'cmdline': 'root=/dev/vda2 rd.plymouth=0 selinux=0',
            'use_initrd': True
        }
    },
    'ubuntu': {
        'x86_64': {
            'repo': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/SelfContained:/ubuntu/images/',
            'system_file': 'Ubuntu-Box.x86_64-System.qcow2',
            'kernel_tar': 'Ubuntu-Box.x86_64-Kernel.tar.xz',
            'cmdline': 'root=/dev/vda3 rd.plymouth=0 selinux=0',
            'use_initrd': True
        },
        'aarch64': {
            'repo': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/SelfContained:/ubuntu/images/',
            'system_file': 'Ubuntu-Box.aarch64-System.qcow2',
            'kernel_tar': 'Ubuntu-Box.aarch64-Kernel.tar.xz',
            'cmdline': 'root=/dev/vda2 rd.plymouth=0 selinux=0',
            'use_initrd': True
        }
    },
    'universal': {
        'x86_64': {
            'repo': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/SelfContained:/universal/images/',
            'system_file': 'Universal-Box.x86_64-System.qcow2',
            'kernel_tar': 'Universal-Box.x86_64-Kernel.tar.xz',
            'cmdline': 'root=/dev/vda3 rd.plymouth=0 selinux=0',
            'use_initrd': True
        },
        'aarch64': {
            'repo': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/SelfContained:/universal/images/',
            'system_file': 'Universal-Box.aarch64-System.qcow2',
            'kernel_tar': 'Universal-Box.aarch64-Kernel.tar.xz',
            'cmdline': 'root=/dev/vda2 rd.plymouth=0 selinux=0',
            'use_initrd': True
        }
    }
}

# Pre-defined image configurations
IMAGE_CONFIGS = {
    'leap15': {
        'desc_dir': './image_descriptions/opensuse_leap_15.6',
        'repo_url': 'https://download.opensuse.org/distribution/leap/15.6/repo/oss'
    },
    'leap16': {
        'desc_dir': './image_descriptions/opensuse_leap_16.0',
        'repo_url': 'https://download.opensuse.org/distribution/leap/16.0/repo/oss'
    }
}


def download_file(url, dest_path):
    print(f"Downloading {url} to {dest_path}...")
    def report_hook(block_num, block_size, total_size):
        read_so_far = block_num * block_size
        if total_size > 0:
            percent = min(100, read_so_far * 100 / total_size)
            sys.stdout.write(f"\rProgress: {percent:.1f}% ({read_so_far / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB)")
        else:
            sys.stdout.write(f"\rDownloaded {read_so_far / (1024*1024):.1f}MB")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, dest_path, reporthook=report_hook)
    print("\nDownload complete.")


def extract_tarball(tar_path, dest_dir, arch):
    print(f"Extracting kernel from {tar_path}...")
    kernel_path = None
    initrd_path = None
    with tarfile.open(tar_path, 'r:xz') as tar:
        for member in tar.getmembers():
            if member.name.endswith('.kernel'):
                member.name = f'kernel.{arch}'
                tar.extract(member, path=dest_dir)
                kernel_path = os.path.join(dest_dir, member.name)
            elif member.name.endswith('.initrd'):
                member.name = f'initrd.{arch}'
                tar.extract(member, path=dest_dir)
                initrd_path = os.path.join(dest_dir, member.name)
    return kernel_path, initrd_path


def unpack_zboot_if_needed(kernel_path):
    if not os.path.isfile(kernel_path):
        return
    try:
        with open(kernel_path, 'rb') as f:
            data = f.read()
        if data[:2] == b'MZ' and b'zimg' in data[:32]:
            start_off = struct.unpack('<I', data[8:12])[0]
            payload_size = struct.unpack('<I', data[12:16])[0]
            comp_type = data[24:32].rstrip(b'\x00')
            decomp = None
            if comp_type == b'zstd':
                payload = data[start_off:start_off + payload_size]
                # Try finding zstd binary or ctypes loading
                for libname in ['libzstd.so.1', 'libzstd.so', 'libzstd.1.dylib', 'libzstd.dylib']:
                    try:
                        libzstd = ctypes.CDLL(libname)
                        libzstd.ZSTD_decompress.argtypes = [
                            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t
                        ]
                        libzstd.ZSTD_decompress.restype = ctypes.c_size_t
                        libzstd.ZSTD_isError.argtypes = [ctypes.c_size_t]
                        libzstd.ZSTD_isError.restype = ctypes.c_uint
                        out_capacity = 256 * 1024 * 1024
                        out_buf = ctypes.create_string_buffer(out_capacity)
                        res = libzstd.ZSTD_decompress(out_buf, out_capacity, payload, len(payload))
                        if not libzstd.ZSTD_isError(res):
                            decomp = out_buf.raw[:res]
                            break
                    except Exception:
                        pass
                
                if not decomp:
                    try:
                        proc = subprocess.Popen(['zstd', '-d', '-c'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        out, _ = proc.communicate(input=payload)
                        if proc.returncode == 0:
                            decomp = out
                    except Exception:
                        pass
            elif comp_type in (b'gzip', b'gz'):
                import gzip
                decomp = gzip.decompress(data[start_off:start_off + payload_size])
            elif comp_type in (b'xz', b'lzma'):
                import lzma
                decomp = lzma.decompress(data[start_off:start_off + payload_size])
            elif comp_type in (b'bz2', b'bzip2'):
                import bz2
                decomp = bz2.decompress(data[start_off:start_off + payload_size])

            if decomp:
                print(f"Unpacked EFI zboot payload ({comp_type.decode('ascii', 'ignore')}) in {kernel_path}")
                with open(kernel_path, 'wb') as f_out:
                    f_out.write(decomp)
    except Exception as e:
        print(f"Warning: Failed to unpack zboot kernel: {e}")


def check_xattr_support(path, index):
    security_model = 'mapped'
    test_file = os.path.join(path, f'.xattr_test_{index}')
    try:
        with open(test_file, 'w') as f:
            f.write('test')
        if hasattr(os, 'setxattr'):
            os.setxattr(test_file, 'user.test_xattr', b'test')
        else:
            raise AttributeError()
        os.remove(test_file)
    except Exception:
        security_model = 'none'
        try:
            os.remove(test_file)
        except Exception:
            pass
    return security_model


def get_qemu_acceleration(accel_arg, arch):
    system = platform.system().lower()
    host_arch = platform.machine()
    
    # Normalize arch names
    normalized_host_arch = 'aarch64' if host_arch in ('arm64', 'aarch64') else 'x86_64'
    normalized_target_arch = 'aarch64' if arch in ('arm64', 'aarch64') else 'x86_64'
    
    if accel_arg == 'false':
        return []
    
    if normalized_host_arch != normalized_target_arch:
        print(f"Note: Target architecture ({normalized_target_arch}) differs from host ({normalized_host_arch}). Emulation mode (no acceleration) is required.")
        return []

    if system == 'darwin':
        return ['-accel', 'hvf']
    elif system == 'linux':
        if os.path.exists('/dev/kvm') and os.access('/dev/kvm', os.R_OK | os.W_OK):
            return ['-accel', 'kvm']
        else:
            print("Warning: /dev/kvm not found or not writable. Running without KVM acceleration.")
            return []
    return []


def get_qemu_machine_and_cpu(arch, has_accel, cpu_arg, machine_arg):
    machine_flags = []
    cpu_flags = []
    
    # Machine model selection
    if machine_arg:
        machine_flags = ['-machine', machine_arg]
    elif arch == 'aarch64':
        machine_flags = ['-machine', 'virt']
        
    # CPU type selection
    if cpu_arg:
        cpu_flags = ['-cpu', cpu_arg]
    elif arch == 'aarch64':
        if has_accel:
            cpu_flags = ['-cpu', 'host']
        else:
            cpu_flags = ['-cpu', 'max']
    elif arch == 'x86_64':
        if has_accel:
            cpu_flags = ['-cpu', 'host']
        else:
            cpu_flags = ['-cpu', 'max']
            
    return machine_flags, cpu_flags


def wait_for_ssh(port, timeout=60):
    start_time = time.time()
    print("Waiting for VM SSH service to start...")
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=2):
                print("VM SSH service is up and responding! Giving it a brief moment to initialize...")
                time.sleep(2)
                return True
        except (socket.timeout, ConnectionRefusedError):
            time.sleep(1)
    return False


def main():
    # Force sys.stdout and sys.stderr to be line-buffered (useful in background/pipes/redirects)
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Run KIWI system boxbuild VM natively on Linux and macOS using QEMU with Paramiko SSH runner."
    )
    parser.add_argument(
        '-i', '--image', default='leap15', choices=['leap15', 'leap16'],
        help="Target OS image configuration to build: 'leap15' (Leap 15.6) or 'leap16' (Leap 16.0) (default: leap15)"
    )
    parser.add_argument(
        '-b', '--box', default='leap', choices=['leap', 'tumbleweed', 'ubuntu', 'universal'],
        help="Name of the box/distribution template to use (default: leap)"
    )
    parser.add_argument(
        '-p', '--profile', default='Vagrant',
        help="KIWI profile to build inside the VM (default: Vagrant)"
    )
    parser.add_argument(
        '-a', '--arch', default='',
        help="Target architecture: 'x86_64' or 'aarch64' (default: host architecture)"
    )
    parser.add_argument(
        '-o', '--output-dir', default='./target_image',
        help="Output directory where the built image will be saved (default: ./target_image)"
    )
    parser.add_argument(
        '-c', '--cache-dir', default='./kiwi_boxes',
        help="Directory where the KIWI boxes are cached (default: ./kiwi_boxes)"
    )
    parser.add_argument(
        '-d', '--desc-dir', default=None,
        help="Directory containing the KIWI image description (default: dynamically set based on --image)"
    )
    parser.add_argument(
        '-r', '--repo-url', default=None,
        help="URL of the package repository to configure in KIWI (default: dynamically set based on --image)"
    )
    parser.add_argument(
        '-m', '--memory', default='8192',
        help="Main memory in MB for the virtual machine (default: 8192)"
    )
    parser.add_argument(
        '-s', '--smp', default='4',
        help="Number of CPU cores for the virtual machine (default: 4)"
    )
    parser.add_argument(
        '--cpu', default='',
        help="Optional CPU model used by QEMU (e.g. host, max)"
    )
    parser.add_argument(
        '--machine', default='',
        help="Optional machine model used by QEMU (e.g. virt)"
    )
    parser.add_argument(
        '--accel', default='auto', choices=['auto', 'true', 'false'],
        help="Enable/disable hardware acceleration: KVM on Linux, HVF on macOS (default: auto)"
    )
    parser.add_argument(
        '--no-parallels', '--without-parallels', action='store_true',
        help="Disable Parallels Guest Tools installation and overlays"
    )
    parser.add_argument(
        '-S', '--parallels-dir', default='./parallels_iso',
        help="Directory containing Parallels Guest Tools ISO (default: ./parallels_iso)"
    )
    parser.add_argument(
        '-l', '--list-boxes', action='store_true',
        help="List all supported build boxes and exit"
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help="Show raw QEMU console boot and system output (otherwise quiet)"
    )
    parser.add_argument(
        '-n', '--dry-run', action='store_true',
        help="Print the native QEMU execution command without launching the VM"
    )
    parser.add_argument(
        '--debug', action='store_true',
        help="Run kiwi-ng inside the guest VM in debug mode (highly verbose)"
    )
    parser.add_argument(
        '--console', action='store_true',
        help="Just start and boot the box VM with SSH/console enabled, without running the automated build"
    )

    args, remaining = parser.parse_known_args()

    # Default with_parallels to True unless disabled explicitly via --no-parallels
    with_parallels = not args.no_parallels

    if args.list_boxes:
        print("Available KIWI Boxes:")
        for box, arch_dict in BOX_CONFIGS.items():
            print(f"  - {box:<12} ({', '.join(arch_dict.keys())})")
        sys.exit(0)

    # Detect architecture
    host_machine = platform.machine()
    default_arch = 'aarch64' if host_machine in ('arm64', 'aarch64') else 'x86_64'
    target_arch = args.arch or default_arch
    if target_arch == 'arm64':
        target_arch = 'aarch64'

    # Auto-adjust box name for aarch64 if default leap box is requested (leap is x86_64 only)
    box_name = args.box
    if target_arch == 'aarch64' and box_name == 'leap':
        print("Note: openSUSE Leap box is x86_64 only. Auto-switching to 'tumbleweed' box for aarch64.")
        box_name = 'tumbleweed'

    # Get box configuration
    if box_name not in BOX_CONFIGS:
        print(f"Error: Box template '{box_name}' is not supported.")
        sys.exit(1)
    if target_arch not in BOX_CONFIGS[box_name]:
        print(f"Error: Architecture '{target_arch}' is not supported for box '{box_name}'.")
        sys.exit(1)
    
    cfg = BOX_CONFIGS[box_name][target_arch]

    # Resolve profile
    profile = args.profile
    if with_parallels and profile == 'Vagrant':
        profile = 'Vagrant-parallels'
        print("Note: Parallels tools requested. Auto-switching profile to 'Vagrant-parallels'.")

    # Get image configuration and resolve defaults
    img_name = args.image
    if img_name not in IMAGE_CONFIGS:
        print(f"Error: Image template '{img_name}' is not supported.")
        sys.exit(1)
    
    img_cfg = IMAGE_CONFIGS[img_name]
    desc_dir = args.desc_dir or img_cfg['desc_dir']
    repo_url = args.repo_url or img_cfg['repo_url']

    # Resolve absolute paths
    abs_desc_dir = os.path.abspath(desc_dir)
    abs_out_dir = os.path.abspath(args.output_dir)
    abs_cache_dir = os.path.abspath(args.cache_dir)
    box_dir = os.path.join(abs_cache_dir, box_name)

    # Ensure directories exist
    os.makedirs(abs_desc_dir, exist_ok=True)
    os.makedirs(abs_out_dir, exist_ok=True)
    os.makedirs(box_dir, exist_ok=True)

    # Handle Parallels overlays
    if with_parallels and args.parallels_dir:
        abs_parallels_dir = os.path.abspath(args.parallels_dir)
        if os.path.isdir(abs_parallels_dir):
            target_overlay_dir = os.path.join(abs_desc_dir, 'root', 'tmp')
            os.makedirs(target_overlay_dir, exist_ok=True)
            symlink_path = os.path.join(target_overlay_dir, 'parallels_iso')
            if os.path.lexists(symlink_path):
                try:
                    if os.path.islink(symlink_path):
                        os.remove(symlink_path)
                    else:
                        shutil.rmtree(symlink_path)
                except Exception:
                    pass
            try:
                # Copy the directory instead of symlinking to allow 9p VM to access the files natively
                shutil.copytree(abs_parallels_dir, symlink_path)
                print(f"Copied parallels_iso directory contents into image description overlay at {symlink_path}")
            except Exception as e:
                print(f"Warning: Failed to copy parallels_iso to overlay: {e}")

    # Define paths for box files
    system_file_name = cfg['system_file']
    system_img_path = os.path.join(box_dir, system_file_name)
    kernel_tar_path = os.path.join(box_dir, cfg['kernel_tar'])
    kernel_path = os.path.join(box_dir, f"kernel.{target_arch}")
    initrd_path = os.path.join(box_dir, f"initrd.{target_arch}") if cfg['use_initrd'] else None

    # Check and download box files if not present
    if not os.path.exists(system_img_path):
        url = cfg['repo'] + system_file_name
        download_file(url, system_img_path)
    
    if not os.path.exists(kernel_path) or (cfg['use_initrd'] and not os.path.exists(initrd_path)):
        if not os.path.exists(kernel_tar_path):
            url = cfg['repo'] + cfg['kernel_tar']
            download_file(url, kernel_tar_path)
        
        extracted_kernel, extracted_initrd = extract_tarball(kernel_tar_path, box_dir, target_arch)
        if extracted_kernel:
            kernel_path = extracted_kernel
        if extracted_initrd:
            initrd_path = extracted_initrd

        # Unpack zboot payload if needed
        unpack_zboot_if_needed(kernel_path)

    # Determine 9p security model for the description and target directory mounts
    desc_security_model = check_xattr_support(abs_desc_dir, 0)
    out_security_model = check_xattr_support(abs_out_dir, 1)

    # Find QEMU binary
    qemu_bin = find_qemu_binary(target_arch)
    if not qemu_bin:
        print(f"Error: QEMU binary for '{target_arch}' ('qemu-system-{target_arch}' or 'qemu-kvm') was not found on your system.")
        print("Please install QEMU using your package manager (e.g. 'brew install qemu' on macOS, 'zypper in qemu-x86' on openSUSE/SLES, or 'apt install qemu-system' on Ubuntu).")
        sys.exit(1)

    # Get QEMU configuration parameters
    accel_flags = get_qemu_acceleration(args.accel, target_arch)
    has_accel = len(accel_flags) > 0
    machine_flags, cpu_flags = get_qemu_machine_and_cpu(target_arch, has_accel, args.cpu, args.machine)

    # Clean up eventual stale exitcode files
    exitcode_file = os.path.join(abs_out_dir, 'result.code')
    if os.path.exists(exitcode_file):
        try:
            os.remove(exitcode_file)
        except Exception:
            pass

    # Extract any extra/remaining arguments (e.g. --type, etc.)
    extra_args = []
    if remaining:
        if remaining[0] == '--':
            extra_args = remaining[1:]
        else:
            extra_args = remaining
    
    extra_cmd = " ".join(extra_args)

    # Build kernel append arguments
    kernel_append = f"{cfg['cmdline']} console=hvc0 kiwi-no-halt kiwi=\"help\""

    # Determine the correct 9p device model based on target architecture
    virtio_9p_device = 'virtio-9p-device' if target_arch == 'aarch64' else 'virtio-9p-pci'

    # Assemble complete QEMU command line
    qemu_cmd = [
        qemu_bin,
        '-m', args.memory,
        '-smp', args.smp,
        '-nographic',
        '-nodefaults',
        '-snapshot'
    ]
    qemu_cmd += accel_flags
    qemu_cmd += machine_flags
    qemu_cmd += cpu_flags
    
    qemu_cmd += [
        '-kernel', kernel_path
    ]
    if initrd_path and os.path.exists(initrd_path):
        qemu_cmd += ['-initrd', initrd_path]

    qemu_cmd += [
        '-append', kernel_append,
        '-drive', f'file={system_img_path},if=virtio,driver=qcow2,cache=off,snapshot=on',
        '-device', 'virtio-serial',
        '-chardev', 'stdio,id=virtiocon0',
        '-device', 'virtconsole,chardev=virtiocon0',
        '-nic', 'user,model=virtio,hostfwd=tcp:127.0.0.1:10022-:22',
        
        # Share description directory
        '-fsdev', f'local,security_model={desc_security_model},id=fsdev0,path={abs_desc_dir}',
        '-device', f'{virtio_9p_device},id=fs0,fsdev=fsdev0,mount_tag=kiwidescription',
        
        # Share output bundle directory
        '-fsdev', f'local,security_model={out_security_model},id=fsdev1,path={abs_out_dir}',
        '-device', f'{virtio_9p_device},id=fs1,fsdev=fsdev1,mount_tag=kiwibundle'
    ]

    print("==================================================")
    print("Native QEMU Box Build VM Configuration:")
    print(f"  QEMU Binary:       {qemu_bin}")
    print(f"  Target Image:      {img_name}")
    print(f"  Box distribution:  {box_name}")
    print(f"  Target Arch:       {target_arch}")
    print(f"  KIWI Profile:      {profile}")
    print(f"  Hardware Accel:    {'Enabled (' + accel_flags[1] + ')' if has_accel else 'Disabled'}")
    print(f"  RAM Allocation:    {args.memory} MB")
    print(f"  CPU Cores (SMP):   {args.smp}")
    print(f"  9p Mount Model:    desc: {desc_security_model}, output: {out_security_model}")
    print(f"  Description Dir:   {abs_desc_dir}")
    print(f"  Output Dir:        {abs_out_dir}")
    print(f"  Cache Dir:         {abs_cache_dir}")
    print(f"  Repository URL:    {repo_url}")
    print(f"  KIWI Debug Mode:   {'Enabled' if args.debug else 'Disabled'}")
    print(f"  Interactive Mode:  {'Console-only (No build)' if args.console else 'Automated Build'}")
    if extra_cmd:
        print(f"  Extra KIWI Args:   {extra_cmd}")
    print("==================================================")

    if args.dry_run:
        print("Dry run enabled. The following QEMU command would be executed:")
        print("--------------------------------------------------")
        print(" ".join(qemu_cmd))
        print("--------------------------------------------------")
        sys.exit(0)

    print("Launching native QEMU box VM...")
    
    # We capture stdin/stdout/stderr to inject SSH config and parse the boot readiness signature dynamically.
    # This avoids connecting to the host slirp port too early, preventing the macOS slirp socket wedging bug.
    try:
        proc = subprocess.Popen(
            qemu_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except Exception as e:
        print(f"Error: Failed to start QEMU: {e}")
        sys.exit(1)

    print("Waiting for VM to boot and start SSH service inside the guest...")
    
    ssh_ready = False
    start_time = time.time()
    boot_timeout = 75
    
    # Start a background thread to periodically send newlines to the guest console.
    # This forces the ready root shell/getty to flush and display its prompt (localhost:~ #).
    import threading
    def tickle_console():
        # Wait 10 seconds initially for the kernel to boot
        time.sleep(10)
        while not ssh_ready:
            try:
                proc.stdin.write("\n")
                proc.stdin.flush()
            except Exception:
                break
            time.sleep(4)
            
    threading.Thread(target=tickle_console, daemon=True).start()
    
    # Read QEMU output line-by-line to look for the boot signature
    while True:
        if proc.poll() is not None:
            print("Error: QEMU process terminated unexpectedly during boot.")
            sys.exit(1)
            
        if time.time() - start_time > boot_timeout:
            print("Error: Timeout waiting for VM boot signature.")
            proc.kill()
            sys.exit(1)
            
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
            
        # If user requested verbose mode, print QEMU output to host console
        if args.verbose:
            sys.stdout.write(line)
            sys.stdout.flush()
            
        # Check for stable boot/login signatures inside the guest OS
        if any(sig in line for sig in ["localhost:~ #", "~ #", "root@", "vagrant@"]):
            print("\nVM has fully booted to the login/prompt screen!")
            
            # Dynamically configure guest sshd and set root password (required on modern Tumbleweed/SLES)
            print("Configuring guest SSH service and setting root password...")
            try:
                # Send a newline to clear prompt, then inject password config, sshd config overrides, and restart sshd
                proc.stdin.write("\n")
                proc.stdin.write("echo 'root:linux' | chpasswd\n")
                proc.stdin.write("mkdir -p /etc/ssh\n")
                proc.stdin.write("cp -n /usr/etc/ssh/sshd_config /etc/ssh/sshd_config\n")
                proc.stdin.write("echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config\n")
                proc.stdin.write("systemctl restart sshd\n")
                proc.stdin.flush()
            except Exception as e:
                print(f"Warning: Failed to inject SSH configuration to guest console: {e}")
                
            print("Allowing guest network and SSH interfaces 5 seconds to settle...")
            time.sleep(5)
            ssh_ready = True
            break

    # Start a background daemon thread to continue consuming QEMU's stdout/stderr
    # so the pipe buffer doesn't fill up and freeze the VM.
    import threading
    def consume_qemu_output(stream, verbose):
        for consume_line in stream:
            if verbose:
                sys.stdout.write(consume_line)
                sys.stdout.flush()
                
    threading.Thread(target=consume_qemu_output, args=(proc.stdout, args.verbose), daemon=True).start()

    print("--------------------------------------------------")
    print("Executing KIWI build inside the VM natively...")
    print("--------------------------------------------------")

    build_status = 0
    ssh_client = None
    
    # Try password 'linux', fallback to 'vagrant' if needed
    passwords = ['linux', 'vagrant']
    connected = False
    
    max_retries = 12
    for attempt in range(1, max_retries + 1):
        for pwd in passwords:
            sock = None
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                # Pre-connect standard IPv4 socket for absolute transport reliability on macOS and Linux
                sock = socket.create_connection(('127.0.0.1', 10022), timeout=15)
                ssh_client.connect(
                    hostname='127.0.0.1',
                    port=10022,
                    username='root',
                    password=pwd,
                    sock=sock,
                    timeout=15,
                    allow_agent=False,
                    look_for_keys=False
                )
                connected = True
                break
            except paramiko.AuthenticationException as e:
                print(f"DEBUG paramiko auth error: {e}")
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
                try:
                    ssh_client.close()
                except Exception:
                    pass
                continue
            except Exception as e:
                print(f"DEBUG paramiko connect error: {type(e).__name__}: {e}")
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
                try:
                    ssh_client.close()
                except Exception:
                    pass
                continue
        if connected:
            break
        print(f"Connecting to VM SSH daemon (attempt {attempt}/{max_retries}). Retrying in 4 seconds...")
        time.sleep(4)

    if not connected:
        print("Error: Failed to connect to VM SSH service after multiple attempts.")
        proc.kill()
        sys.exit(1)

    if args.console:
        print("\n==================================================")
        print("[ INFO    ]: QEMU Box VM is booted and ready!")
        print("  - Host SSH Port:   10022")
        print("  - Credentials:     root / linux (or vagrant / vagrant)")
        print("  - SSH Command:")
        print("    ssh root@127.0.0.1 -p 10022 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null")
        print("==================================================")
        
        # Mount the shared folders inside the VM automatically for the user
        try:
            ssh_client.exec_command(
                "mkdir -p /description /bundle && "
                "mountpoint -q /description || mount -t 9p -o trans=virtio,version=9p2000.L,msize=262144 kiwidescription /description && "
                "mountpoint -q /bundle || mount -t 9p -o trans=virtio,version=9p2000.L,msize=262144 kiwibundle /bundle"
            )
            print("[ INFO    ]: Automatically mounted shared directories under /description and /bundle inside guest.")
        except Exception as e:
            print(f"Warning: Failed to automatically mount directories inside VM: {e}")
            
        print("==================================================")
        print("VM is running in interactive manual mode.")
        print("Press Ctrl+C to terminate and gracefully shutdown the VM.")
        print("==================================================")
        
        try:
            while proc.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nInteractive VM session interrupted by user.")
        
        print("\n--------------------------------------------------")
        print("Shutting down VM...")
        print("--------------------------------------------------")
        try:
            transport = ssh_client.get_transport()
            chan_off = transport.open_session()
            chan_off.exec_command("poweroff")
            chan_off.close()
        except Exception:
            pass
        
        try:
            ssh_client.close()
        except Exception:
            pass
            
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            print("Force terminating QEMU process...")
            proc.kill()
            
        result_code_path = os.path.join(abs_out_dir, 'result.code')
        try:
            with open(result_code_path, 'w') as f:
                f.write("0\n")
        except Exception:
            pass
        sys.exit(0)

    debug_flag = "--debug" if args.debug else ""

    remote_script = f"""
set -e
echo "[ INFO    ]: Mounting shared folders inside VM..."
mkdir -p /description /bundle /result
mountpoint -q /description || mount -t 9p -o trans=virtio,version=9p2000.L,msize=262144 kiwidescription /description
mountpoint -q /bundle || mount -t 9p -o trans=virtio,version=9p2000.L,msize=262144 kiwibundle /bundle

echo "[ INFO    ]: Cleaning up guest build directory..."
rm -rf /result/*

echo "[ INFO    ]: Starting KIWI build inside VM..."
kiwi-ng {debug_flag} --logfile /bundle/result.log --profile {profile} system build --description /description --target-dir /result --set-repo {repo_url} {extra_cmd}

echo "[ INFO    ]: Bundling build results back to host..."
kiwi-ng result bundle --id 0 --target-dir /result --bundle-dir /bundle
"""

    transport = ssh_client.get_transport()
    channel = transport.open_session()
    
    # Request a pseudo-terminal to enable live, line-buffered logs and progress bars
    channel.get_pty()
    channel.exec_command(remote_script)

    # Real-time stdout stream
    try:
        while True:
            if channel.recv_ready():
                data = channel.recv(4096)
                if not data:
                    break
                sys.stdout.write(data.decode('utf-8', errors='ignore'))
                sys.stdout.flush()
            if channel.recv_stderr_ready():
                data = channel.recv_stderr(4096)
                sys.stderr.write(data.decode('utf-8', errors='ignore'))
                sys.stderr.flush()
            if channel.exit_status_ready():
                break
            time.sleep(0.01)

        # Drain remaining buffer
        while channel.recv_ready():
            data = channel.recv(4096)
            sys.stdout.write(data.decode('utf-8', errors='ignore'))
            sys.stdout.flush()

        build_status = channel.recv_exit_status()
    except KeyboardInterrupt:
        print("\nBuild process interrupted by user.")
        build_status = 130
    finally:
        channel.close()

    print("\n--------------------------------------------------")
    print("Shutting down VM...")
    print("--------------------------------------------------")
    
    # Send graceful poweroff
    try:
        chan_off = transport.open_session()
        chan_off.exec_command("poweroff")
        chan_off.close()
    except Exception:
        pass

    ssh_client.close()

    # Wait for QEMU process to terminate
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        print("Force terminating QEMU process...")
        proc.kill()

    # Archive build log exactly as build-image.sh does
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_log = f"result-{profile}-{target_arch}-{timestamp}.log"
    result_log = os.path.join(abs_out_dir, 'result.log')
    
    if os.path.exists(result_log):
        try:
            shutil.move(result_log, os.path.join(abs_out_dir, unique_log))
            print(f"Build log saved to: {os.path.join(args.output_dir, unique_log)}")
        except Exception as e:
            print(f"Warning: Failed to rename build log: {e}")

    # Write status code to result.code for automated runner compatibility
    try:
        with open(exitcode_file, 'w') as f:
            f.write(f"{build_status}\n")
    except Exception:
        pass

    if build_status == 0:
        print("\nNative QEMU Box build completed successfully!")
    else:
        print("\n==================================================", file=sys.stderr)
        print("Error: Native QEMU Box build failed inside VM!", file=sys.stderr)
        unique_log_path = os.path.join(abs_out_dir, unique_log)
        if os.path.exists(unique_log_path):
            print(f"Last 10 lines from {unique_log_path}:", file=sys.stderr)
            print("--------------------------------------------------", file=sys.stderr)
            try:
                with open(unique_log_path, 'r', errors='ignore') as log_f:
                    lines = log_f.readlines()
                    for line in lines[-10:]:
                        sys.stderr.write(line)
            except Exception:
                pass
            print("--------------------------------------------------", file=sys.stderr)
        print("==================================================", file=sys.stderr)
    
    # Clean up any copied Parallels overlay files to keep the description directory clean
    if with_parallels and args.parallels_dir:
        target_overlay_dir = os.path.join(abs_desc_dir, 'root', 'tmp')
        symlink_path = os.path.join(target_overlay_dir, 'parallels_iso')
        if os.path.exists(symlink_path):
            try:
                shutil.rmtree(symlink_path)
                print("Cleaned up copied parallels_iso overlay directory.")
            except Exception as e:
                print(f"Warning: Failed to clean up parallels_iso overlay: {e}")

    sys.exit(build_status)


def find_qemu_binary(arch):
    # Try standard PATH search
    binary = shutil.which(f"qemu-system-{arch}")
    if binary:
        return binary
    binary = shutil.which("qemu-kvm")
    if binary:
        return binary
        
    # On macOS, try common Homebrew installation paths if not in PATH
    if platform.system().lower() == 'darwin':
        for prefix in ['/opt/homebrew/bin', '/usr/local/bin']:
            path = os.path.join(prefix, f"qemu-system-{arch}")
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
                
    return None


if __name__ == '__main__':
    main()
