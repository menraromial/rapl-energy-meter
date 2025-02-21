#!/bin/bash

# Check if the user is root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    echo "Use: sudo $0"
    exit 1
fi

# Function to display detailed CPU core status
show_detailed_cpu_status() {
    echo "Detailed CPU core status:"
    echo "-------------------------"
    echo "Total number of cores: $(nproc --all)"
    echo "Online cores: $(cat /sys/devices/system/cpu/online)"
    echo "Offline cores: $(cat /sys/devices/system/cpu/offline 2>/dev/null || echo 'none')"
    echo "-------------------------"

    for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
        if [ -d "$cpu" ]; then
            cpu_num=${cpu##*/cpu}
            echo -n "CPU$cpu_num: "
            
            # Check if the core is online
            if [ -f "$cpu/online" ]; then
                status=$(cat "$cpu/online")
                if [ "$status" -eq 1 ]; then
                    echo -n "Active"
                else
                    echo -n "Inactive"
                fi
            else
                echo -n "Always active (main core)"
            fi
            
            # Display current frequency if available
            if [ -f "$cpu/cpufreq/scaling_cur_freq" ]; then
                cur_freq=$(cat "$cpu/cpufreq/scaling_cur_freq")
                cur_freq_mhz=$(echo "scale=2; $cur_freq/1000" | bc)
                echo -n ", Frequency: ${cur_freq_mhz}MHz"
            fi
            
            echo ""
        fi
    done
}

# Function to display governor information
show_governor_info() {
    echo "CPU governor configuration:"
    echo "-------------------------"
    if [ -f "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor" ]; then
        governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
        echo "Current governor: $governor"
        echo "Available governors: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors)"
    else
        echo "Governor information not available"
    fi
}

# Function to enable a core
enable_cpu() {
    local cpu_num=$1
    if [ -f "/sys/devices/system/cpu/cpu$cpu_num/online" ]; then
        echo 1 > "/sys/devices/system/cpu/cpu$cpu_num/online"
        echo "CPU$cpu_num enabled"
    else
        echo "Unable to enable CPU$cpu_num (main or non-existent core)"
    fi
}

# Function to disable a core
disable_cpu() {
    local cpu_num=$1
    if [ -f "/sys/devices/system/cpu/cpu$cpu_num/online" ]; then
        echo 0 > "/sys/devices/system/cpu/cpu$cpu_num/online"
        echo "CPU$cpu_num disabled"
    else
        echo "Unable to disable CPU$cpu_num (main or non-existent core)"
    fi
}

# Function to change the governor
change_governor() {
    read -p "Enter the new governor ($(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors)): " new_governor
    for cpu in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
        echo "$new_governor" > "$cpu" 2>/dev/null
    done
    echo "Governor changed to: $new_governor"
}

# Main menu
while true; do
    clear
    echo "=== Advanced CPU Core Manager ==="
    echo "1. Display detailed core status"
    echo "2. Enable a core"
    echo "3. Disable a core"
    echo "4. Enable a range of cores"
    echo "5. Disable a range of cores"
    echo "6. Enable all cores"
    echo "7. Disable all cores (except CPU0)"
    echo "8. Display/Change CPU governor"
    echo "9. Exit"
    
    read -p "Choose an option (1-9): " choice
    
    case $choice in
        1)
            show_detailed_cpu_status
            show_governor_info
            ;;
        2)
            read -p "Enter the core number to enable (1-21): " cpu_num
            if [ "$cpu_num" -ge 1 ] && [ "$cpu_num" -le 21 ]; then
                enable_cpu $cpu_num
            else
                echo "Invalid core number"
            fi
            ;;
        3)
            read -p "Enter the core number to disable (1-21): " cpu_num
            if [ "$cpu_num" -ge 1 ] && [ "$cpu_num" -le 21 ]; then
                disable_cpu $cpu_num
            else
                echo "Invalid core number"
            fi
            ;;
        4)
            read -p "Enter the first core of the range (1-21): " start
            read -p "Enter the last core of the range (1-21): " end
            if [ "$start" -ge 1 ] && [ "$end" -le 21 ] && [ "$start" -le "$end" ]; then
                for ((i=start; i<=end; i++)); do
                    enable_cpu $i
                done
            else
                echo "Invalid range"
            fi
            ;;
        5)
            read -p "Enter the first core of the range (1-21): " start
            read -p "Enter the last core of the range (1-21): " end
            if [ "$start" -ge 1 ] && [ "$end" -le 21 ] && [ "$start" -le "$end" ]; then
                for ((i=start; i<=end; i++)); do
                    disable_cpu $i
                done
            else
                echo "Invalid range"
            fi
            ;;
        6)
            for i in {1..21}; do
                enable_cpu $i
            done
            ;;
        7)
            for i in {1..21}; do
                disable_cpu $i
            done
            ;;
        8)
            show_governor_info
            read -p "Do you want to change the governor? (y/n): " change
            if [ "$change" = "y" ]; then
                change_governor
            fi
            ;;
        9)
            echo "Goodbye!"
            exit 0
            ;;
        *)
            echo "Invalid option"
            ;;
    esac
    
    read -p "Press Enter to continue..."
done
