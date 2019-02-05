#!/bin/bash
systemctl stop nginx
certbot renew
systemctl start nginx