import socket
import ssl
import threading
import smtplib
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as DjangoEmailBackend

class EmailBackend(DjangoEmailBackend):
    def open(self):
        """
        Ensure an open connection to the email server. Return whether or not a
        new connection was required (True or False) or None if an exception
        passed silently.
        
        Overridden to fix Python 3.12 compatibility (ssl_keyfile/certfile removed from smtplib).
        """
        if self.connection:
            # Nothing to do if the connection is already open.
            return False

        # If local_hostname is not specified, socket.getfqdn() gets used.
        # For performance, we use the cached FQDN for local_hostname.
        connection_params = {"local_hostname": socket.getfqdn()}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
            
        if self.use_ssl:
            # Python 3.12 removed keyfile/certfile args
            if self.ssl_keyfile or self.ssl_certfile:
                context = ssl.create_default_context()
                context.load_cert_chain(certfile=self.ssl_certfile, keyfile=self.ssl_keyfile)
                connection_params["context"] = context
            
        try:
            self.connection = self.connection_class(
                self.host, self.port, **connection_params
            )

            # TLS/SSL are mutually exclusive, so only attempt TLS over
            # non-secure connections.
            if not self.use_ssl and self.use_tls:
                if self.ssl_keyfile or self.ssl_certfile:
                    context = ssl.create_default_context()
                    context.load_cert_chain(certfile=self.ssl_certfile, keyfile=self.ssl_keyfile)
                    self.connection.starttls(context=context)
                else:
                    # In Python 3.12, starttls() takes no keyfile/certfile args
                    self.connection.starttls()

            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise
