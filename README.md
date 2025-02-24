# RAPL Process Energy Tracer

This Python script traces the energy consumption of a specified process using RAPL (Running Average Power Limit) and exports the data to CSV files. It provides detailed monitoring of power consumption across different hardware domains including CPU cores, integrated GPU, and DRAM.

## Features

- Real-time monitoring of process energy consumption
- Tracks multiple RAPL domains (Package, CPU Cores, GPU, DRAM)
- Configurable sampling interval
- Optional CSV export of energy and power data
- Detailed power consumption statistics
- Process CPU usage and state monitoring
- Verbose debugging options

## Requirements

- Linux operating system with RAPL support (most modern Intel processors)
- Python 3.6 or higher (if using the script)
- Root privileges (for MSR register access)
- MSR module enabled (`sudo modprobe msr`)

## Installation

### Option 1: Using Pre-built Binary

1. Download the pre-built binary:
```bash
wget https://github.com/menraromial/rapl-energy-meter/releases/download/<version>/rapl-energy-meter
```

2. Make the binary executable:
```bash
chmod +x rapl-energy-meter
```

3. Enable the MSR module:
```bash
sudo modprobe msr
```

### Option 2: From Source

1. Clone the repository:
```bash
git clone https://github.com/menraromial/rapl-energy-meter.git
cd rapl-energy-meter
```

2. Make sure the MSR module is loaded:
```bash
sudo modprobe msr
```

## Usage

### Using the Binary

```bash
sudo ./rapl-energy-meter DURATION [OPTIONS]
```

### Using the Python Script

Basic usage:
```bash
sudo python3 main.py DURATION
```

Full options:
```bash
sudo python3 main.py [-h] [-i INTERVAL] [-v] [--csv] [--output-dir OUTPUT_DIR] [-p pid] duration
```

### Arguments

- `pid`: Process ID to monitor
- `duration`: Duration of monitoring in seconds
- `-i, --interval`: Sampling interval in seconds (default: 1.0, minimum: 0.001)
- `-v`: Increase verbosity level (can be repeated)
- `--csv`: Enable CSV export of trace data
- `--output-dir`: Output directory for CSV files

### Example

Monitor process 1234 for 60 seconds with 0.5s sampling interval and CSV export:
```bash
# Using binary
sudo ./rapl-energy-meter 60 -p 1234 -i 0.5 --csv

# Using Python script
sudo python3 main.py 60 -p 1234 -i 0.5 --csv
```

## Output Files

When CSV export is enabled, the script generates three files:

1. `energy_trace_pidXXXX_YYYYMMDD_HHMMSS_energy.csv`: Energy consumption data
2. `energy_trace_pidXXXX_YYYYMMDD_HHMMSS_power.csv`: Power consumption data
3. `energy_trace_pidXXXX_YYYYMMDD_HHMMSS_summary.csv`: Statistical summary

### CSV Format

#### Energy/Power CSV
```
timestamp,package,core,uncore,dram,cpu
0.000,0.123456,0.098765,0.045678,0.034567,0
1.001,0.234567,0.187654,0.056789,0.045678,2
...
```

#### Summary CSV
```
domain,total_energy,avg_power,max_power,min_power
Package,12.345678,2.345678,3.456789,1.234567
CPU Cores,8.901234,1.789012,2.345678,0.890123
...
```

## Technical Details

The script uses RAPL MSR (Model-Specific Registers) to access energy consumption data:

- `MSR_RAPL_POWER_UNIT (0x606)`: Power units
- `MSR_PKG_ENERGY_STATUS (0x611)`: Package energy
- `MSR_PP0_ENERGY_STATUS (0x639)`: CPU cores energy
- `MSR_PP1_ENERGY_STATUS (0x641)`: Uncore energy
- `MSR_DRAM_ENERGY_STATUS (0x619)`: DRAM energy
- `MSR_PSYS_ENERGY_STATUS (0x64d)`: Psys

## Limitations

- Requires root privileges
- Only works on Linux systems with RAPL support
- Some RAPL domains might not be available on all processors
- Energy readings wrap around after reaching their maximum value (handled by the script)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the BSD 2-Clause License - see the LICENSE file for details.

## Acknowledgments

- Intel for RAPL technology
- Linux kernel developers for exposing RAPL interfaces

## Authors

- Menra W. Romial (@menraromial)