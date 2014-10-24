#!/usr/bin/env python

import argparse, imp, importlib, os, socket
from tinc import *

def main():

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
    parser_init.add_argument('-b', '--bucket')
    parser_init.set_defaults(func=init)

    parser_update = subparsers.add_parser('update')
    parser_update.add_argument('-d', '--directory', default='/etc/tinc/')
    parser_update.set_defaults(func=update)

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

    network_path = os.path.join(args.directory, args.network)

    # create network directories, continue if they already exist
    hosts_dir = os.path.join(args.directory, args.network, 'hosts')
    try: 
        os.makedirs(hosts_dir)
    except OSError:
        if not os.path.isdir(hosts_dir):
            raise

    # setup s3 connection
    import boto
    conn = boto.connect_s3()
    
    # get config file from bucket
    if args.bucket:
        bucket_name = args.bucket
    else:
        bucket_name = args.network

    bucket = conn.get_bucket(bucket_name)
    
    config_filename = args.network+'.py'
    print "Downloading config file %s." % config_filename
    config_path = os.path.join(network_path, config_filename)
    config_key = bucket.get_key(config_filename)
    config_key.get_contents_to_filename(config_path)    

    # import module with same name as network
    network_module = imp.load_source(args.network, config_path)

    # get network object, also same name as network
    network = getattr(network_module, args.network)

    # abort if host not defined in config file
    if not network.groups[0].get_node(args.hostname):
        print "Error: Node %s not defined in config file, aborting." % args.hostname
        exit(1)

    # write config file and scripts
    tinc_conf_filename = os.path.join(network_path, 'tinc.conf')
    print "Writing %s" % tinc_conf_filename
    tinc_conf = open(tinc_conf_filename, 'w')
    tinc_conf.write(network.generate_tinc_conf(args.hostname))
    tinc_conf.close()

    # write config file and scripts
    tinc_up_filename = os.path.join(network_path, 'tinc-up')
    print "Writing %s" % tinc_up_filename
    tinc_up = open(tinc_up_filename, 'w')
    os.chmod(tinc_up_filename, 0744)
    tinc_up.write(network.generate_tinc_up(args.hostname))
    tinc_up.close()

    # write config file and scripts
    tinc_down_filename = os.path.join(network_path, 'tinc-down')
    print "Writing %s" % tinc_down_filename
    tinc_down = open(tinc_down_filename, 'w')
    os.chmod(tinc_down_filename, 0744)
    tinc_down.write(network.generate_tinc_down())
    tinc_down.close()

    # generate keypair if one doesn't exist already
    privkey_filename = os.path.join(args.directory, network.name, 'rsa_key.priv')
    if not os.path.isfile(privkey_filename):
        print "Private key not found, creating one."
        from Crypto.PublicKey import RSA
        RSAkey = RSA.generate(2048)
        privkey_file = open(privkey_filename, 'w')
        privkey_file.write(RSAkey.exportKey())
        privkey_file.close()
        os.chmod(privkey_filename, 0400)

        pubkey_key = "hosts/%s" % args.hostname
        if bucket.get_key(pubkey_key):
            print "WARNING: Public key already exists on S3, making a copy and overwriting it."
            bucket.copy_key(pubkey_key+'.old', bucket.name, pubkey_key)

        pubkey_key = bucket.new_key(pubkey_key)
        print "Uploading public key to S3."
        pubkey_key.set_contents_from_string(RSAkey.publickey().exportKey())
        pubkey_key.close()

    update_hosts(network, bucket, hosts_dir)

def update_hosts(network, bucket, hosts_dir):
    # generate host files from S3 keys and write to hosts dir 
    for node in network.groups[0].nodes:
        pubkey_key = bucket.get_key("hosts/%s" % node.name)
        if pubkey_key is None:
            print "WARNING: public key for %s not found." % node.name
            continue
        pubkey = pubkey_key.get_contents_as_string()
        pubkey_filename = os.path.join(hosts_dir, node.name)
        print "Writing public key file %s" % pubkey_filename
        keyfile = open(pubkey_filename, 'w')
        keyfile.write(pubkey)
        keyfile.write("\n")
        keyfile.write("Subnet = %s\n" % node.subnet.cidr)
        keyfile.write("Address = %s\n" % node.address)
        keyfile.close()
        os.chmod(pubkey_filename, 0400)

def update(args):

    # config directories
    network_path = os.path.join(args.directory, args.network)
    hosts_dir = os.path.join(network_path, 'hosts')
    config_path = os.path.join(network_path, args.network+'.py')

    # import module with same name as network
    network_module = imp.load_source(args.network, config_path)

    # get network object, also same name as network
    network = getattr(network_module, args.network)

    # initialize bucket
    import boto
    conn = boto.connect_s3()
    bucket = conn.get_bucket(network.bucket)

    # write config file and scripts
    tinc_conf_filename = os.path.join(network_path, 'tinc.conf')
    print "Writing %s" % tinc_conf_filename
    tinc_conf = open(tinc_conf_filename, 'w')
    tinc_conf.write(network.generate_tinc_conf(args.hostname))
    tinc_conf.close()

    update_hosts(network, bucket, hosts_dir)

if __name__ == "__main__":
    main()