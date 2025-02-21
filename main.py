#!/usr/bin/env python3
import os
import struct
import sys
import time
import argparse
import csv
from collections import defaultdict
from datetime import datetime

# RAPL registers
MSR_RAPL_POWER_UNIT = 0x606
MSR_PKG_ENERGY_STATUS = 0x611
MSR_PP0_ENERGY_STATUS = 0x639  # CPU cores
MSR_PP1_ENERGY_STATUS = 0x641  # Uncore
MSR_DRAM_ENERGY_STATUS = 0x619  # DRAM
MSR_PSYS_ENERGY_STATUS = 0x64d  # Platform/System level power (available on some systems)


class RaplDomain:
    def __init__(self, name, msr_address):
        self.name = name
        self.msr_address = msr_address
        self.total_energy = 0
        self.last_reading = None
        self.intervals = []

class ProcessEnergyTracer:
    def __init__(self, pid=None, sample_interval=1.0, verbose_level=0, export_csv=False, output_dir=None):
        self.pid = pid
        self.cpu = 0
        self.verbose = verbose_level
        self.sample_interval = sample_interval
        self.export_csv = export_csv
        self.output_dir = output_dir
        
        self.domains = {
            'package': RaplDomain('Package', MSR_PKG_ENERGY_STATUS),
            'cpu': RaplDomain('CPU Cores', MSR_PP0_ENERGY_STATUS),
            'uncore': RaplDomain('Uncore', MSR_PP1_ENERGY_STATUS),
            'dram': RaplDomain('DRAM', MSR_DRAM_ENERGY_STATUS),
            'psys': RaplDomain('Platform Total', MSR_PSYS_ENERGY_STATUS)
        }
        self._initialize_rapl()
    
    def debug(self, level, message):
        """Display debug message if verbosity level is sufficient"""
        if self.verbose >= level:
            print(f"[DEBUG-{level}] {message}")

    def _initialize_rapl(self):
        """Initialize RAPL units"""
        self.debug(2, "Initializing RAPL units...")
        units = self.read_msr(MSR_RAPL_POWER_UNIT)
        self.energy_units = 1.0 / (1 << ((units >> 8) & 0xf))
        print(f"RAPL energy units: {self.energy_units:.6f} Joules")
        self.debug(2, f"Raw POWER_UNIT register value: 0x{units:X}")

    def read_msr(self, register):
        """Read an MSR register"""
        try:
            with open(f"/dev/cpu/{self.cpu}/msr", "rb") as f:
                f.seek(register)
                value = struct.unpack('Q', f.read(8))[0]
                self.debug(3, f"Reading MSR 0x{register:X}: 0x{value:X}")
                return value
        except IOError as e:
            self.debug(1, f"Error reading MSR 0x{register:X}: {e}")
            return None

    def read_energy_all_domains(self):
        """Read energy from all RAPL domains"""
        self.debug(2, "Reading energy for all domains")
        readings = {}
        for domain_name, domain in self.domains.items():
            value = self.read_msr(domain.msr_address)
            if value is not None:
                energy = value * self.energy_units
                readings[domain_name] = energy
                self.debug(3, f"Domain {domain_name}: {energy:.6f}J (raw: 0x{value:X})")
        return readings

    def get_process_info(self):
        """Get detailed process information"""
        if self.pid is None:
            return None
        
        try:
            self.debug(2, f"Reading information for PID {self.pid}")
            
            # Read status
            with open(f"/proc/{self.pid}/status", "r") as f:
                status = dict(line.split(':\t') for line in f.read().split('\n') if line and ':\t' in line)
                self.debug(3, f"Status: {status}")
            
            # Read stat
            with open(f"/proc/{self.pid}/stat", "r") as f:
                stat = f.read().split()
                self.debug(3, f"Stat: {stat}")
            
            # Read schedstat
            with open(f"/proc/{self.pid}/schedstat", "r") as f:
                runtime, waittime, timeslices = map(int, f.read().strip().split())
                self.debug(3, f"Schedstat: runtime={runtime}, waittime={waittime}, slices={timeslices}")
            
            info = {
                'state': stat[2],
                'cpu': int(stat[38]) if len(stat) > 38 else -1,
                'runtime': runtime,
                'voluntary_switches': int(status.get('voluntary_ctxt_switches', '0').strip()),
                'nonvoluntary_switches': int(status.get('nonvoluntary_ctxt_switches', '0').strip())
            }
            self.debug(2, f"Process information: {info}")
            return info
            
        except FileNotFoundError:
            self.debug(1, f"Process {self.pid} not found!")
            return None
        except Exception as e:
            self.debug(1, f"Error reading process info: {e}")
            return None

    def export_to_csv(self):
        """Export trace data to CSV files in matrix format"""
        if not self.export_csv:
            return
            
        if self.output_dir is None:
            self.output_dir = os.getcwd()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"energy_trace_pid{self.pid}_{timestamp}"
        
        # Create timestamp-indexed dictionary to group data
        energy_data = defaultdict(dict)
        power_data = defaultdict(dict)
        cpu_data = defaultdict(int)
        
        # Collect data
        for domain_name, domain in self.domains.items():
            for interval in domain.intervals:
                t = f"{interval['time']:.3f}"
                energy_data[t][domain_name] = interval['energy']
                power_data[t][domain_name] = interval['power']
                cpu_data[t] = interval['cpu']
        
        # Export energy data
        energy_file = os.path.join(self.output_dir, f"{base_filename}_energy.csv")
        with open(energy_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'package', 'core', 'uncore', 'dram','psys', 'cpu'])
            
            for t in sorted(energy_data.keys(), key=float):
                writer.writerow([
                    t,
                    f"{energy_data[t].get('package', 0):.6f}",
                    f"{energy_data[t].get('cpu', 0):.6f}",
                    f"{energy_data[t].get('uncore', 0):.6f}",
                    f"{energy_data[t].get('dram', 0):.6f}",
                    f"{energy_data[t].get('psys', 0):.6f}",
                    cpu_data[t]
                ])
        
        # Export power data
        power_file = os.path.join(self.output_dir, f"{base_filename}_power.csv")
        with open(power_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'package', 'core', 'uncore', 'dram','psys', 'cpu'])
            
            for t in sorted(power_data.keys(), key=float):
                writer.writerow([
                    t,
                    f"{power_data[t].get('package', 0):.6f}",
                    f"{power_data[t].get('cpu', 0):.6f}",
                    f"{power_data[t].get('uncore', 0):.6f}",
                    f"{power_data[t].get('dram', 0):.6f}",
                    f"{power_data[t].get('psys', 0):.6f}",
                    cpu_data[t]
                ])
        
        # Export summary
        summary_file = os.path.join(self.output_dir, f"{base_filename}_summary.csv")
        with open(summary_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['domain', 'total_energy', 'avg_power', 'max_power', 'min_power'])
            
            for domain_name, domain in self.domains.items():
                if domain.intervals:
                    powers = [interval['power'] for interval in domain.intervals]
                    avg_power = sum(powers) / len(powers)
                    max_power = max(powers)
                    min_power = min(powers)
                    
                    writer.writerow([
                        domain.name,
                        f"{domain.total_energy:.6f}",
                        f"{avg_power:.6f}",
                        f"{max_power:.6f}",
                        f"{min_power:.6f}"
                    ])
        
        print(f"\nCSV export completed:")
        print(f"- Energy data: {energy_file}")
        print(f"- Power data: {power_file}")
        print(f"- Summary: {summary_file}")

    def trace_energy(self, duration):
        """Trace energy for specified duration"""
        start_time = time.time()
        last_runtime = 0
        last_check_time = start_time
        
        print(f"\nStarting trace for PID {self.pid}...")
        
        # Display available domains
        print("Available RAPL domains:")
        for domain_name, domain in self.domains.items():
            if self.read_msr(domain.msr_address) is not None:
                print(f"- {domain.name}")
        
        # Initial state
        print("\nInitial process state:")
        initial_info = self.get_process_info()
        if initial_info:
            for key, value in initial_info.items():
                print(f"{key}: {value}")
        
        # Initial reading
        initial_readings = self.read_energy_all_domains()
        last_readings = initial_readings.copy()
        self.debug(1, f"Initial readings: {initial_readings}")
        
        try:
            while (time.time() - start_time) < duration:
                current_time = time.time()
                elapsed = current_time - last_check_time
                
                if elapsed >= self.sample_interval:
                    info = self.get_process_info()
                    current_readings = self.read_energy_all_domains()
                    runtime_diff = 0

                    if info:
                        self.debug(1, "Process terminated")
                        runtime_diff = info['runtime'] - last_runtime
                        self.debug(2, f"Runtime diff: {runtime_diff/1e9:.3f}s")
                    
                    if runtime_diff > 0:
                        print(f"\nElapsed time: {current_time - start_time:.1f}s")
                        print(f"CPU {info['cpu']}, State: {info['state']}")
                        if self.verbose >= 1:
                            print(f"Context switches - V: {info['voluntary_switches']}, NV: {info['nonvoluntary_switches']}")
                        print(f"CPU time used: {runtime_diff/1e9:.3f}s")


                    if runtime_diff > 0 or self.pid is None:

                        for domain_name in current_readings.keys():
                            energy_diff = current_readings[domain_name] - last_readings[domain_name]
                            power = energy_diff / elapsed
                            
                            self.debug(2, (f"Domain {domain_name} - "
                                         f"Previous: {last_readings[domain_name]:.6f}J, "
                                         f"Current: {current_readings[domain_name]:.6f}J"))
                            
                            print(f"{self.domains[domain_name].name}:")
                            print(f"  Energy: {energy_diff:.3f}J")
                            print(f"  Power: {power:.3f}W")
                            
                            self.domains[domain_name].intervals.append({
                                'time': current_time - start_time,
                                'energy': energy_diff,
                                'power': power,
                                'cpu': info['cpu'] if self.pid else self.cpu
                            })
                            self.domains[domain_name].total_energy += energy_diff
                    
                    if self.pid:
                        last_runtime = info['runtime']
                    last_readings = current_readings
                    last_check_time = current_time
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nUser interruption - generating final report...")
        
        # Final summary
        print("\n=== Trace Summary ===")
        for domain_name, domain in self.domains.items():
            if domain.intervals:
                print(f"\n{domain.name}:")
                print(f"Total energy: {domain.total_energy:.3f}J")
                
                powers = [interval['power'] for interval in domain.intervals]
                if powers:
                    avg_power = sum(powers) / len(powers)
                    max_power = max(powers)
                    min_power = min(powers)
                    print(f"Average power: {avg_power:.3f}W")
                    print(f"Max power: {max_power:.3f}W")
                    print(f"Min power: {min_power:.3f}W")
                    
                    if self.verbose >= 1:
                        print("\nInterval details:")
                        for interval in domain.intervals:
                            print(f"  t={interval['time']:.1f}s: "
                                  f"{interval['power']:.3f}W on CPU {interval['cpu']}")
        
        # Optional CSV export
        if self.export_csv:
            self.export_to_csv()

def main():
    parser = argparse.ArgumentParser(description='RAPL energy tracer for processes')
    #parser.add_argument('pid', type=int, help='PID of process to trace')
    parser.add_argument('duration', type=float, help='Trace duration in seconds')
    parser.add_argument('-p', '--pid', type=int, help='PID of process to monitor (optional)')
    parser.add_argument('-i', '--interval', type=float, default=1.0,
                        help='Sampling interval in seconds (default: 1.0, min: 0.001)')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='Verbosity level (repeat to increase)')
    parser.add_argument('--csv', action='store_true',
                        help='Enable CSV export of trace data')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for CSV files')
    args = parser.parse_args()

    if args.interval < 0.001:
        print("Sampling interval cannot be less than 1ms")
        sys.exit(1)

    if os.geteuid() != 0:
        print("This program must be run with sudo")
        sys.exit(1)

    tracer = ProcessEnergyTracer(
        pid=args.pid, 
        sample_interval=args.interval, 
        verbose_level=args.verbose, 
        export_csv=args.csv, 
        output_dir=args.output_dir
        )
    tracer.trace_energy(duration=args.duration)

if __name__ == "__main__":
    main()