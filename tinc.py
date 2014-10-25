from netaddr import IPAddress, IPNetwork

class vpn:
    def __init__(self, name, subnet, bucket):
        self.name = name
        self.subnet = IPNetwork(subnet)
        self.bucket = bucket
        self.groups = list()

    def add_group(self):
        new_group = group()
        self.groups.append(new_group)
        return new_group

    def generate_tinc_conf(self, hostname):
        config  = "Name = %s\n" % hostname
        config += "\n"
        for node in self.groups[0].nodes:
            if node.name == hostname:
                continue
            config += "ConnectTo = %s\n" % node.name
        return config

    def generate_tinc_up(self, hostname):
        config  = "#!/bin/bash\n"
        config += "\n"
        config += "ifconfig $INTERFACE %s netmask %s\n" % (
                    self.groups[0].get_node(hostname).subnet.ip,
                    self.subnet.netmask )

        return config

    def generate_tinc_down(self):
        config  = "#!/bin/bash\n"
        config += "\n"
        config += "ifconfig $INTERFACE down\n"
        return config

    def deploy(self):
        pass

class group:
    def __init__(self):
        self.nodes = list()

    def add_node(self, **kwargs):
        self.nodes.append(node(**kwargs))

    def get_node(self, name):
        for node in self.nodes:
            if node.name == name:
                return node

class node:
    def __init__(self, name, address, subnet):
        self.name = name
        self.address = address
        self.subnet = IPNetwork(subnet)
