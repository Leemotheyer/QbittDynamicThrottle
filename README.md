Dynamically throttle QBittorrent speeds, based on jellyfin and minecraft

Install with docker:  
```
image: leemotheyer/qbittdynamicthrottle:latest
container_name: qbt-throttle-control
restart: unless-stopped
ports:
  - "5000:5000"
volumes:
- ./config.yaml:/app/config.yaml
environment:
  - TZ=Europe/London
```

Then access the web gui on the configured port
