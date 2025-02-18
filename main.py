#!/usr/bin/env python3
import os
import struct
import sys
import time
import argparse
import csv
from collections import defaultdict
from datetime import datetime

#  Registres RAPL
MSR_RAPL_POWER_UNIT = 0x606
MSR_PKG_ENERGY_STATUS = 0x611
MSR_PP0_ENERGY_STATUS = 0x639  # CPU cores
MSR_PP1_ENERGY_STATUS = 0x641  # GPU intégré
MSR_DRAM_ENERGY_STATUS = 0x619  # DRAM

class RaplDomain:
    def __init__(self, name, msr_address):
        self.name = name
        self.msr_address = msr_address
        self.total_energy = 0
        self.last_reading = None
        self.intervals = []

class ProcessEnergyTracer:
    def __init__(self, pid, sample_interval=1.0, verbose_level=0):
        self.pid = pid
        self.cpu = 0
        self.verbose = verbose_level
        self.sample_interval = sample_interval
        self.domains = {
            'package': RaplDomain('Package', MSR_PKG_ENERGY_STATUS),
            'cpu': RaplDomain('CPU Cores', MSR_PP0_ENERGY_STATUS),
            'gpu': RaplDomain('GPU intégré', MSR_PP1_ENERGY_STATUS),
            'dram': RaplDomain('DRAM', MSR_DRAM_ENERGY_STATUS)
        }
        self._initialize_rapl()
    
    def debug(self, level, message):
        """Affiche un message de debug si le niveau de verbosité est suffisant"""
        if self.verbose >= level:
            print(f"[DEBUG-{level}] {message}")

    def _initialize_rapl(self):
        """Initialise les unités RAPL"""
        self.debug(2, "Initialisation des unités RAPL...")
        units = self.read_msr(MSR_RAPL_POWER_UNIT)
        self.energy_units = 1.0 / (1 << ((units >> 8) & 0xf))
        print(f"Unités d'énergie RAPL: {self.energy_units:.6f} Joules")
        self.debug(2, f"Valeur brute du registre POWER_UNIT: 0x{units:X}")

    def read_msr(self, register):
        """Lit un registre MSR"""
        try:
            with open(f"/dev/cpu/{self.cpu}/msr", "rb") as f:
                f.seek(register)
                value = struct.unpack('Q', f.read(8))[0]
                self.debug(3, f"Lecture MSR 0x{register:X}: 0x{value:X}")
                return value
        except IOError as e:
            self.debug(1, f"Erreur lecture MSR 0x{register:X}: {e}")
            return None

    def read_energy_all_domains(self):
        """Lit l'énergie de tous les domaines RAPL"""
        self.debug(2, "Lecture de l'énergie pour tous les domaines")
        readings = {}
        for domain_name, domain in self.domains.items():
            value = self.read_msr(domain.msr_address)
            if value is not None:
                energy = value * self.energy_units
                readings[domain_name] = energy
                self.debug(3, f"Domaine {domain_name}: {energy:.6f}J (raw: 0x{value:X})")
        return readings

    def get_process_info(self):
        """Obtient les informations détaillées du processus"""
        try:
            self.debug(2, f"Lecture des informations pour PID {self.pid}")
            
            # Lecture du statut
            with open(f"/proc/{self.pid}/status", "r") as f:
                status = dict(line.split(':\t') for line in f.read().split('\n') if line and ':\t' in line)
                self.debug(3, f"Status: {status}")
            
            # Lecture de stat
            with open(f"/proc/{self.pid}/stat", "r") as f:
                stat = f.read().split()
                self.debug(3, f"Stat: {stat}")
            
            # Lecture de schedstat
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
            self.debug(2, f"Informations processus: {info}")
            return info
            
        except FileNotFoundError:
            self.debug(1, f"Processus {self.pid} non trouvé!")
            return None
        except Exception as e:
            self.debug(1, f"Erreur lecture infos processus: {e}")
            return None

    def export_to_csv(self, output_dir=None):
        """Exporte les données de traçage en fichiers CSV avec un format matriciel"""
        if output_dir is None:
            output_dir = os.getcwd()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"energy_trace_pid{self.pid}_{timestamp}"
        
        # Création d'un dictionnaire indexé par timestamp pour regrouper les données
        energy_data = defaultdict(dict)
        power_data = defaultdict(dict)
        cpu_data = defaultdict(int)
        
        # Collecte des données
        for domain_name, domain in self.domains.items():
            for interval in domain.intervals:
                t = f"{interval['time']:.3f}"
                energy_data[t][domain_name] = interval['energy']
                power_data[t][domain_name] = interval['power']
                cpu_data[t] = interval['cpu']
        
        # Export des données d'énergie
        energy_file = os.path.join(output_dir, f"{base_filename}_energy.csv")
        with open(energy_file, 'w', newline='') as f:
            writer = csv.writer(f)
            # En-tête
            writer.writerow(['timestamp', 'package', 'core', 'gpu', 'dram', 'cpu'])
            
            # Données triées par timestamp
            for t in sorted(energy_data.keys(), key=float):
                writer.writerow([
                    t,
                    f"{energy_data[t].get('package', 0):.6f}",
                    f"{energy_data[t].get('cpu', 0):.6f}",
                    f"{energy_data[t].get('gpu', 0):.6f}",
                    f"{energy_data[t].get('dram', 0):.6f}",
                    cpu_data[t]
                ])
        
        # Export des données de puissance
        power_file = os.path.join(output_dir, f"{base_filename}_power.csv")
        with open(power_file, 'w', newline='') as f:
            writer = csv.writer(f)
            # En-tête
            writer.writerow(['timestamp', 'package', 'core', 'gpu', 'dram', 'cpu'])
            
            # Données triées par timestamp
            for t in sorted(power_data.keys(), key=float):
                writer.writerow([
                    t,
                    f"{power_data[t].get('package', 0):.6f}",
                    f"{power_data[t].get('cpu', 0):.6f}",
                    f"{power_data[t].get('gpu', 0):.6f}",
                    f"{power_data[t].get('dram', 0):.6f}",
                    cpu_data[t]
                ])
        
        # Export du résumé maintenu pour référence
        summary_file = os.path.join(output_dir, f"{base_filename}_summary.csv")
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
        
        print(f"\nExport CSV terminé:")
        print(f"- Données d'énergie: {energy_file}")
        print(f"- Données de puissance: {power_file}")
        print(f"- Résumé: {summary_file}")

    def trace_energy(self, duration):
        """Trace l'énergie pendant la durée spécifiée"""
        start_time = time.time()
        last_runtime = 0
        last_check_time = start_time
        
        print(f"\nDémarrage du traçage pour le PID {self.pid}...")
        
        # Affiche les domaines disponibles
        print("Domaines RAPL disponibles:")
        for domain_name, domain in self.domains.items():
            if self.read_msr(domain.msr_address) is not None:
                print(f"- {domain.name}")
        
        # État initial
        print("\nÉtat initial du processus:")
        initial_info = self.get_process_info()
        if initial_info:
            for key, value in initial_info.items():
                print(f"{key}: {value}")
        
        # Lecture initiale
        initial_readings = self.read_energy_all_domains()
        last_readings = initial_readings.copy()
        self.debug(1, f"Lectures initiales: {initial_readings}")
        
        try:
            while (time.time() - start_time) < duration:
                current_time = time.time()
                elapsed = current_time - last_check_time
                
                if elapsed >= self.sample_interval:  # Vérification par defaut toutes les secondes
                    info = self.get_process_info()
                    if info is None:
                        self.debug(1, "Processus terminé")
                        break
                    
                    current_readings = self.read_energy_all_domains()
                    runtime_diff = info['runtime'] - last_runtime
                    
                    self.debug(2, f"Runtime diff: {runtime_diff/1e9:.3f}s")
                    
                    if runtime_diff > 0:
                        print(f"\nTemps écoulé: {current_time - start_time:.1f}s")
                        print(f"CPU {info['cpu']}, État: {info['state']}")
                        if self.verbose >= 1:
                            print(f"Changements contexte - V: {info['voluntary_switches']}, NV: {info['nonvoluntary_switches']}")
                        print(f"Temps CPU utilisé: {runtime_diff/1e9:.3f}s")
                        
                        # Mesures d'énergie
                        for domain_name in current_readings.keys():
                            energy_diff = current_readings[domain_name] - last_readings[domain_name]
                            power = energy_diff / elapsed
                            
                            self.debug(2, (f"Domaine {domain_name} - "
                                         f"Précédent: {last_readings[domain_name]:.6f}J, "
                                         f"Actuel: {current_readings[domain_name]:.6f}J"))
                            
                            print(f"{self.domains[domain_name].name}:")
                            print(f"  Énergie: {energy_diff:.3f}J")
                            print(f"  Puissance: {power:.3f}W")
                            
                            self.domains[domain_name].intervals.append({
                                'time': current_time - start_time,
                                'energy': energy_diff,
                                'power': power,
                                'cpu': info['cpu']
                            })
                            self.domains[domain_name].total_energy += energy_diff
                    
                    last_runtime = info['runtime']
                    last_readings = current_readings
                    last_check_time = current_time
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nInterruption utilisateur - génération du rapport final...")
        
        # Résumé final
        print("\n=== Résumé du traçage ===")
        for domain_name, domain in self.domains.items():
            if domain.intervals:
                print(f"\n{domain.name}:")
                print(f"Énergie totale: {domain.total_energy:.3f}J")
                
                powers = [interval['power'] for interval in domain.intervals]
                if powers:
                    avg_power = sum(powers) / len(powers)
                    max_power = max(powers)
                    min_power = min(powers)
                    print(f"Puissance moyenne: {avg_power:.3f}W")
                    print(f"Puissance max: {max_power:.3f}W")
                    print(f"Puissance min: {min_power:.3f}W")
                    
                    if self.verbose >= 1:
                        print("\nDétails des intervalles:")
                        for interval in domain.intervals:
                            print(f"  t={interval['time']:.1f}s: "
                                  f"{interval['power']:.3f}W sur CPU {interval['cpu']}")
        
        # Export des données en CSV
        self.export_to_csv()

def main():
    parser = argparse.ArgumentParser(description='Traceur d\'énergie RAPL pour processus')
    parser.add_argument('pid', type=int, help='PID du processus à tracer')
    parser.add_argument('duration', type=float, help='Durée du traçage en secondes')
    parser.add_argument('-i', '--interval', type=float, default=1.0,
                        help='Intervalle d\'échantillonnage en secondes (par défaut: 1.0, min: 0.001)')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='Niveau de verbosité (répéter pour augmenter)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Répertoire de sortie pour les fichiers CSV')
    args = parser.parse_args()

    # Vérification de l'intervalle minimum
    if args.interval < 0.001:
        print("L'intervalle d'échantillonnage ne peut pas être inférieur à 1ms")
        sys.exit(1)

    if os.geteuid() != 0:
        print("Ce programme doit être exécuté avec sudo")
        sys.exit(1)

    tracer = ProcessEnergyTracer(args.pid, args.interval, args.verbose)
    tracer.trace_energy(args.duration)

if __name__ == "__main__":
    main()