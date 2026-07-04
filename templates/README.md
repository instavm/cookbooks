# Devbox templates

- LibreChat is deferred because docker-compose inside the VM is blocked.
- OpenGauss is pending verified install steps.
- code-server is the only template with open egress (`allow_domains: "*"`): a general-purpose IDE needs arbitrary git hosts, package registries, and the extension marketplace. Users can narrow the list for locked-down deployments.
