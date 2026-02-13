# ------------------------------------------------------------
# Extra redirects on :443 to the TAK frontdoor on :8446
# Keep this file small and explicit; add new paths as discovered.
# ------------------------------------------------------------

# Marti
location = /Marti {
    return 302 https://$host:8446/Marti;
}
location = /Marti/ {
    return 302 https://$host:8446/Marti/;
}
location ^~ /Marti/ {
    return 302 https://$host:8446$request_uri;
}

# WebTAK (both cases seen in the wild)
location = /webtak {
    return 302 https://$host:8446/webtak;
}
location = /webtak/ {
    return 302 https://$host:8446/webtak/;
}
location ^~ /webtak/ {
    return 302 https://$host:8446$request_uri;
}

location = /WebTak {
    return 302 https://$host:8446/WebTak;
}
location = /WebTak/ {
    return 302 https://$host:8446/WebTak/;
}
location ^~ /WebTak/ {
    return 302 https://$host:8446$request_uri;
}

# OAuth paths (WebTAK)
location ^~ /oauth/ {
    return 302 https://$host:8446$request_uri;
}

# Login redirects (observed: /login/refresh)
location = /login {
    return 302 https://$host:8446/login;
}
location = /login/ {
    return 302 https://$host:8446/login/;
}
location ^~ /login/ {
    return 302 https://$host:8446$request_uri;
}

# Observed after Marti login (your screenshot): https://<host>/index.html on :443
location = /index.html {
    return 302 https://$host:8446/Marti;
}

# Convenience: root on :443 should keep going to takctl
# (If Marti ever redirects to "/" on :443, we still want takctl as the landing)
# NOTE: actual "/" is already handled as 404 by default in takctl vhost.
# Add a redirect if we start seeing "/" redirects from Marti:
# location = / { return 302 https://$host/takctl/; }

