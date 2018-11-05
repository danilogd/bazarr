from get_argv import config_dir

from get_settings import get_general_settings

import os
import logging
import sqlite3

import git

current_working_directory = os.path.dirname(os.path.dirname(__file__))

def gitconfig():
    g = git.Repo.init(current_working_directory)
    config_read = g.config_reader()
    config_write = g.config_writer()
    
    try:
        username = config_read.get_value("user", "name")
    except:
        logging.debug('BAZARR Settings git username')
        config_write.set_value("user", "name", "Bazarr")
    
    try:
        email = config_read.get_value("user", "email")
    except:
        logging.debug('BAZARR Settings git email')
        config_write.set_value("user", "email", "bazarr@fake.email")

def check_and_apply_update():
    gitconfig()
    branch = get_general_settings()[5]
    g = git.cmd.Git(current_working_directory)
    g.fetch('origin')
    result = g.diff('--shortstat', 'origin/' + branch)
    if len(result) == 0:
        logging.info('BAZARR No new version of Bazarr available.')
    else:
        g.reset('--hard', 'HEAD')
        g.checkout(branch)
        g.reset('--hard','origin/' + branch)
        g.pull()
        logging.info('BAZARR Updated to latest version. Restart required. ' + result)
        updated()

def updated():
    conn = sqlite3.connect(os.path.join(config_dir, 'db/bazarr.db'), timeout=30)
    c = conn.cursor()
    c.execute("UPDATE system SET updated = 1")
    conn.commit()
    c.close()