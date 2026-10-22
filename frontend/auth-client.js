/* SPDX-License-Identifier: AGPL-3.0-only
 * Host supplies a short-lived bearer in memory, scoped to one explicit backend origin.
 * Never take credentials from query strings or browser persistence.
 */
(function () {
  "use strict";
  function configuredURL(base) {
    const url = new URL(base, window.location.href);
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (url.username || url.password || url.search || url.hash ||
        (url.protocol !== "https:" && !(url.protocol === "http:" && local)) ||
        window.BELAY_AUTH_ORIGIN !== url.origin) {
      throw new Error("Host authentication is not configured for this backend");
    }
    if (window.BELAY_SESSION_PROXY === true &&
        (url.origin !== new URL(window.location.href).origin ||
         url.pathname.replace(/\/$/, "") !== "/belay/api")) {
      throw new Error("Host authentication is not configured for this backend");
    }
    return url;
  }
  window.BelayAuth = {
    credentials(base) {
      if (window.BELAY_SESSION_PROXY !== true) return undefined;
      configuredURL(base);
      return "same-origin";
    },
    async headers(base) {
      configuredURL(base);
      if (window.BELAY_SESSION_PROXY === true) {
        const matches = document.cookie.split(";").map(part => part.trim()).filter(part => part.startsWith("_xsrf="));
        let xsrf;
        try { xsrf = matches.length === 1 ? decodeURIComponent(matches[0].slice(6)) : ""; }
        catch { xsrf = ""; }
        if (!/^[\x21-\x7e]{1,4096}$/.test(xsrf)) throw new Error("Notebook session verification is unavailable");
        return {"Content-Type": "application/json", "X-XSRFToken": xsrf};
      }
      if (typeof window.BELAY_GET_ACCESS_TOKEN !== "function") {
        throw new Error("Host authentication is not configured for this backend");
      }
      const token = await window.BELAY_GET_ACCESS_TOKEN();
      if (typeof token !== "string" || !token || /[\r\n]/.test(token)) {
        throw new Error("Host authentication did not provide an access token");
      }
      const headers = { "Content-Type": "application/json", Authorization: "Bearer " + token };
      if (window.BELAY_INSTITUTION_ID && window.BELAY_CLASS_ID) {
        headers["X-Belay-Institution"] = window.BELAY_INSTITUTION_ID;
        headers["X-Belay-Class"] = window.BELAY_CLASS_ID;
      }
      return headers;
    }
  };
})();
