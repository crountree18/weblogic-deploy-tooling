"""
Copyright (c) 2017, 2023, Oracle Corporation and/or its affiliates.  All rights reserved.
Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.
"""
import re, os
from xml.dom.minidom import parse
from wlsdeploy.exception import exception_helper

from wlsdeploy.logging.platform_logger import PlatformLogger
import wlsdeploy.util.unicode_helper as str_helper
from wlsdeploy.aliases.model_constants import DRIVER_PARAMS_NET_SSL_VERSION_VALUE

_logger = PlatformLogger('wlsdeploy.create')

def set_ssl_properties(xml_doc, atp_creds_path, keystore_password, truststore_password, keystore, keystore_type,
                       truststore, truststore_type):
    '''
    Add SSL config properties to the specified XML document.
    :param xml_doc:                 The XML document
    :param db_keystore_password:    The DB keystore/truststore password (assumed to be same)
    :return: void
    '''
    dom_tree = parse(xml_doc)
    collection = dom_tree.documentElement
    props = collection.getElementsByTagName("propertySet")

    keystore, keystore_type, truststore, truststore_type = fix_store_type_and_default_value(keystore, keystore_type,
                                                                                            truststore, truststore_type)

    for prop in props:
        if prop.getAttribute('name') == 'props.db.1':
            set_property(dom_tree, prop, 'oracle.net.ssl_server_dn_match', 'true')
            set_property(dom_tree, prop, 'oracle.net.ssl_version', DRIVER_PARAMS_NET_SSL_VERSION_VALUE)
            set_property(dom_tree, prop, 'oracle.net.tns_admin', atp_creds_path)
            set_property(dom_tree, prop, 'javax.net.ssl.trustStoreType', truststore_type)
            set_property(dom_tree, prop, 'javax.net.ssl.keyStoreType', keystore_type)
            if not os.path.isabs(keystore):
                set_property(dom_tree, prop, 'javax.net.ssl.keyStore', atp_creds_path + keystore)
            else:
                set_property(dom_tree, prop, 'javax.net.ssl.keyStore', keystore)
            if not os.path.isabs(truststore):
                set_property(dom_tree, prop, 'javax.net.ssl.trustStore', atp_creds_path + truststore)
            else:
                set_property(dom_tree, prop, 'javax.net.ssl.trustStore', truststore)

            if keystore_password is not None:
                set_property(dom_tree, prop, 'javax.net.ssl.keyStorePassword', keystore_password)
            if truststore_password is not None:
                set_property(dom_tree, prop, 'javax.net.ssl.trustStorePassword', truststore_password)
            # Persist the changes in the xml file
            file_handle = open(xml_doc, "w")
            dom_tree.writexml(file_handle)
            file_handle.close()


def fix_store_type_and_default_value(keystore, keystore_type, truststore, truststore_type):
    # historical reason atp does not need these inputs by default and it uses JKS
    # set the default and return it
    if truststore is None:
        truststore = "truststore.jks"
    if keystore is None:
        keystore = "keystore.jks"
    if truststore_type is None:
        truststore_type = "JKS"
    if keystore_type is None:
        keystore_type = "JKS"
    return keystore, keystore_type, truststore, truststore_type


def set_property(dom_tree, prop, name, value):
    '''
    Sets the property child element under prop parent node.
    :param dom_tree: The DOM document handle
    :param prop:    The propertySet parent handle
    :param name:    The property name
    :param value:   The property value
    :return: void
    '''
    property_element = dom_tree.createElement('property')
    property_element.setAttribute("name", name)
    property_element.setAttribute("value", value)
    prop.appendChild(property_element)
    newline = dom_tree.createTextNode('\n')
    prop.appendChild(newline)

def fix_jps_config(rcu_db_info, model_context):
    tns_admin = rcu_db_info.get_tns_admin()
    keystore_password = rcu_db_info.get_keystore_password()
    truststore_password = rcu_db_info.get_truststore_password()
    keystore_type = rcu_db_info.get_keystore_type()
    truststore_type = rcu_db_info.get_truststore_type()
    keystore = rcu_db_info.get_keystore()
    truststore = rcu_db_info.get_truststore()

    jps_config = model_context.get_domain_home() + '/config/fmwconfig/jps-config.xml'
    jps_config_jse = model_context.get_domain_home() + '/config/fmwconfig/jps-config-jse.xml'
    set_ssl_properties(jps_config, tns_admin, keystore_password, truststore_password, keystore, keystore_type,
                       truststore, truststore_type)
    set_ssl_properties(jps_config_jse, tns_admin, keystore_password, truststore_password, keystore, keystore_type,
                       truststore, truststore_type)


def get_atp_connect_string(tnsnames_ora_path, tns_sid_name):
    try:
        f = open(tnsnames_ora_path, "r")
        try:
            text = f.read()
        finally:
            f.close()
        # The regex below looks for the <dbName>_<level><whitespaces>=<whitespaces> and grabs the
        # tnsConnectString from the current and the next line as tnsnames.ora file has the connect string
        # being printed on 2 lines.
        pattern = tns_sid_name + '\s*=\s*([(].*\n.*)'
        match = re.search(pattern, text)
        if match:
            connect_string = match.group(1)
            tns_connect_string = connect_string.replace('\r','').replace('\n','')
            connect_string = cleanup_connect_string(tns_connect_string)
            return connect_string, None
        else:
            ex = exception_helper.create_create_exception("WLSDPLY-12563", tns_sid_name)
            _logger.throwing(ex, class_name='atp_helper', method_name='get_atp_connect_string')
            raise ex
    except IOError, ioe:
        ex = exception_helper.create_create_exception("WLSDPLY-12570", str_helper.to_string(ioe))
        _logger.throwing(ex, class_name='atp_helper', method_name='get_atp_connect_string')
        raise ex
    except Exception, ex:
        ex = exception_helper.create_create_exception("WLSDPLY-12570", str_helper.to_string(ex))
        _logger.throwing(ex, class_name='atp_helper', method_name='get_atp_connect_string')
        raise ex

def cleanup_connect_string(connect_string):
    """
    Formats connect string for ATP DB by removing unwanted whitespaces. It appears the wallet's tnsnames.ora file in
    the wallet has various whitespaces from various periods.  The cie code somehow parses this connection string also,
    so this is the best effort to remove the spaces.

    Input:
        (description= (address=(protocol=tcps)(port=1522)(host=*******.oraclecloud.com))(connect_data=(service_name=someservice-in.oraclecloud.com))(security=(ssl_server_cert_dn= "CN=somewhere-in.oraclecloud.com,OU=Oracle BMCS US,O=Oracle Corporation,L=Redwood City,ST=California,C=US")) )
       or
        (description= (retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=*******.oraclecloud.com))(connect_data=(service_name=someservice-in.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
    Output Parts:
        1.      (description=(address=(protocol=tcps)(port=1522)(host=*******.oraclecloud.com))(connect_data=(service_name=someservice-in.oraclecloud.com))(security=(
        2.      ssl_server_cert_dn=
        3.      "CN=somewhere-in.oraclecloud.com,OU=Oracle BMCS US,O=Oracle Corporation,L=Redwood City,ST=California,C=US"
        4.      )))
    :param connect_string:
    :return: fixed connection string without white spaces
    """

    result = ''
    if connect_string.find("(ssl_server_cert_dn=") > 0:
        toks = connect_string.split('(description=')
        # can have multiples
        pattern = "(.*)(ssl_server_cert_dn=)\s*(\".*\")(.*)"
        for token in toks:
            if token.find("(ssl_server_cert_dn=") > 0:
                match = re.search(pattern, token)
                if match:
                    part1 = match.group(1).replace(' ','')
                    part2 = match.group(2).replace(' ', '')
                    # We don't want to remove the spaces from serverDN part.
                    part3 = match.group(3)
                    part4 = match.group(4).replace(' ', '')
                    result += "(description=%s%s%s%s" % (part1, part2, part3, part4)
            else:
                result += token.replace(' ', '')
    else:
        result = connect_string.replace(' ','')

    return result

