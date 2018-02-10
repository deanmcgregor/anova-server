Designed to be used with a modified homebridge-anova module (see forked repo).

Server based on pycirculate example.

Reqirements
===========
 * bluepy
 * flask
 * pycirculate (pip install git+https://github.com/erikcw/pycirculate.git)

Setup
=====

1. Run ``sudo hcitool lescan`` to find your Anvoa's MAC address
2. Modify the MAC address inside server.py
3. Start server

Server runs on port 5000 by default.
