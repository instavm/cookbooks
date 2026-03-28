const dns = require("node:dns");

const originalLookup = dns.lookup.bind(dns);
const originalPromiseLookup = dns.promises.lookup.bind(dns.promises);

function rewriteHost(hostname) {
  return hostname === "localhost" ? "127.0.0.1" : hostname;
}

dns.lookup = function patchedLookup(hostname, options, callback) {
  if (typeof options === "function") {
    return originalLookup(rewriteHost(hostname), options);
  }
  return originalLookup(rewriteHost(hostname), options, callback);
};

dns.promises.lookup = function patchedPromiseLookup(hostname, options) {
  return originalPromiseLookup(rewriteHost(hostname), options);
};
