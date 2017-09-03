#!/usr/bin/python

import atexit
import argparse
import glob
import logging
import os, os.path
import subprocess
import sys
import time

def check_pid(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def query_user(query, opts):
    lower_opts = map(lambda s: s.lower(), opts)
    while True:
        response = raw_input("{} ".format(query)).lower()
        if response in lower_opts:
            return opts[lower_opts.index(response)]
        if len(opts) <= 1:
            return None

def load_daemon(path):
    daemon = {}
    with open(path, 'r') as fp:
        daemon['pid'] = None
        for line in fp.readlines():
            temp = line.rstrip().split('=', 1)
            if len(temp) != 2:
                temp.append(None)
            key, value = temp
            if key.startswith('argv_'):
                index = int(key.split('_')[1])
                if 'argv' not in daemon:
                    daemon['argv'] = {}
                daemon['argv'][index] = value
            elif key == 'pidfile':
                if os.path.isfile(value):
                    with open(value, 'r') as fp:
                        pid = int(fp.readline().rstrip())
                    if check_pid(pid):
                        daemon['pid'] = pid
        if 'argv' in daemon:
            daemon['argv'] = daemon['argv'].values()
        else:
            daemon['argv'] = []
    return daemon
    
def load_daemons():
    services = {}
    for path in glob.glob('/var/run/openrc/started/*'):
        name = os.path.basename(path)
        services[name] = {}
        services[name]['status'] = 'started'
        services[name]['daemons'] = []

        for daemon in glob.glob('/var/run/openrc/daemons/{}/*'.format(name)):
            daemon = load_daemon(path)
            services[name]['daemons'].append(daemon)
            if daemon['pid'] == None:
                services[name]['status'] = 'stopped'
    return services

def check_daemons(required):
    daemons = load_daemons()
    missing = set()
    for service in required:
        if (service in daemons.keys() and daemons[service]['status'] == 'stopped') \
           or service not in daemons.keys():
            missing.add(service)
    return missing

def switch_runlevel(runlevel):
    subprocess.call(['/sbin/openrc', runlevel])

def runlevel_services(runlevel):
    for path in glob.glob('/etc/runlevels/{}/*'.format(runlevel)):
        yield os.path.basename(path)

def monitor_runlevel(runlevel, timeout, handler=None):
    monitor_services(list(runlevel_services(runlevel)), timeout, handler)

def monitor_services(services, timeout, handler=None):

    while True:
        missing = check_daemons(services)

        if len(missing) > 0:
            logging.info('Services are missing: {}'.format(', '.join(list(missing))))
        else:
            logging.debug('Status check was completed')
            
        if handler != None:
            if len(missing) > 0:
                handler(status='failure', services=missing)
            else:
                handler(status='success', services=None)
        else:
            if len(missing) > 0:
                break

        try:
            logging.debug('Sleeping until next poll in {}s'.format(timeout))
            time.sleep(timeout)
        except KeyboardInterrupt as ex:
            if "Y" == query_user("Are you sure you want to quit? (Y/N)", ["Y","N"]):
                logging.info("User requested exit, shutting down")
                break

def supervise_runlevel(default, shutdown, timeout):
    logging.info('Starting supervision of runlevel {}, timeout {}s'.format(default, timeout))
    atexit.register(lambda: switch_runlevel(shutdown))

    logging.debug('Switching to the default runlevel {}'.format(default))
    switch_runlevel(default)

    logging.debug('Starting monitoring of services')
    monitor_runlevel(default, timeout)

    logging.info('Monitoring stopped, exiting')

def start_services(services):
    for service in services:
        subprocess.call(["/sbin/service", service, "start"])

def stop_services(services):
    for service in services:
        subprocess.call(["/sbin/service", service, "stop"])

def supervise_services(services, timeout):
    logging.info('Starting supervision of services {}, timeout {}s'.format(', '.join(services), timeout))
    atexit.register(lambda: stop_services(services))

    logging.debug('Starting services {}'.format(', '.join(services)))
    start_services(services)

    logging.debug('Starting monitoring of services')
    monitor_services(services, timeout)

    logging.info('Monitoring stopped, exiting')


def main():
    parser = argparse.ArgumentParser(description='Supervise OpenRC services')
    parser.add_argument('-v', '--verbose', help='increase output verbosity', action="store_true")
    parser.add_argument('-r', '--default-runlevel', metavar='DEFAULT_LEVEL', help='the runlevel used when starting up', type=str, default=None)
    parser.add_argument('-k', '--shutdown-runlevel', metavar='SHUTDOWN_LEVEL', help='the runlevel used when shutting down', type=str, default=None)
    parser.add_argument('-s', '--services', metavar='SERVICES', nargs='+', help='run services instead of runlevel', type=str)
    parser.add_argument('-t', '--timeout', metavar='SECONDS', help='time to sleep between checks', type=int, default=30)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if (args.default_runlevel == None or default_runlevel == None) \
       and (args.services == None):
        parser.print_help()
        sys.exit(0)

    if args.services != None:
        logging.info('Services were specified; supervising services')
        supervise_services(args.services, args.timeout)
    else:
        logging.info('Services were not specified; supervising runlevel')
        supervise_runlevel(args.default_runlevel, args.shutdown_runlevel, args.timeout)

if __name__ == "__main__":
    main()
