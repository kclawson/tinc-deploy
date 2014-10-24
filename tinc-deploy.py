#!/usr/bin/env python

import argparse, importlib, os, socket
from tinc import *

def main():
    # print "Network construction machine v0.0."

    parser = argparse.ArgumentParser()
    parser.add_argument('network',  
        help='network name')
    parser.add_argument('-n', '--hostname', default=socket.gethostname())

    subparsers = parser.add_subparsers()

    parser_dump_all = subparsers.add_parser('dump-all', 
                    help='show raw network info')
    parser_dump_all.set_defaults(func=dump)
    
    parser_generate = subparsers.add_parser('generate', 
                    help='generate configuration files')
    parser_generate.add_argument('config_file')
    parser_generate.set_defaults(func=generate)

    parser_init = subparsers.add_parser('init')
    parser_init.add_argument('-d', '--directory', default='/etc/tinc/')
    parser_init.set_defaults(func=init)

    args = parser.parse_args()
    args.func(args) 

def dump(args):
    network_module = importlib.import_module(args.network)
    network = getattr(network_module, args.network)
    print "Name = " + network.name
    print "Network = " + network.subnet

def generate(args):
    network_module = importlib.import_module(args.network)
    network = getattr(network_module, args.network)

    if args.config_file == "tinc.conf":
        print network.generate_tinc_conf(args.hostname)
    elif args.config_file == "tinc-up":
        print network.generate_tinc_up(args.hostname)
    elif args.config_file == "tinc-down":
        print network.generate_tinc_down()   

def init(args):
    
    # import module with same name as network
    network_module = importlib.import_module(args.network)

    # get network object, also same name as network
    network = getattr(network_module, args.network)

    # abort if host not defined in config file
    if not network.groups[0].get_node(args.hostname):
        print "Error: Node %s not defined in config file, aborting." % args.hostname
        exit(1)

    # create network directories, continue if they already exist
    hosts_dir = os.path.join(args.directory, network.name, 'hosts')
    try: 
        os.makedirs(hosts_dir)
    except OSError:
        if not os.path.isdir(hosts_dir):
            raise

    # initialize s3 connection
    import boto
    conn = boto.connect_s3()
    bucket = conn.get_bucket(network.bucket)

    # generate keypair if one doesn't exist already
    privkey_filename = os.path.join(args.directory, network.name, 'rsa_key.priv')
    if not os.path.isfile(privkey_filename):
        print "Private key not found, creating one."
        from Crypto.PublicKey import RSA
        RSAkey = RSA.generate(2048)
        privkey_file = open(privkey_filename, 'w')
        privkey_file.write(RSAkey.exportKey())

        pubkey_key = "hosts/%s" % args.hostname
        if bucket.get_key(pubkey_key):
            print "Warning: Public key already exists on S3, making a copy and overwriting it."
            bucket.copy_key(pubkey_key+'.old', bucket.name, pubkey_key)

        pubkey_key = bucket.new_key(pubkey_key)
        pubkey_key.set_contents_from_string(RSAkey.publickey().exportKey())
        pubkey_key.close()

    # generate host files from S3 keys and write to hosts dir 
    for node in network.groups[0].nodes:
        print "Generating public key file in hosts/%s" % node.name
        pubkey_key = bucket.get_key("hosts/%s" % node.name)
        if pubkey_key is None:
            print "Warning: public key for %s not found." % node.name
            continue
        pubkey = pubkey_key.get_contents_as_string()
        keyfile = open(os.path.join(hosts_dir, node.name), 'w')
        keyfile.write(pubkey)
        keyfile.write("\n")
        keyfile.write("Subnet = %s\n" % node.subnet)
        keyfile.write("Address = %s\n" % node.address)
        keyfile.close()

if __name__ == "__main__":
    main()