import click
import os
from configparser import ConfigParser
from xdg import xdg_config_home

def configCreate():
    config_path = xdg_config_home() / 'shred-project-helper/sph.ini'
    config = ConfigParser()

    if not os.path.exists(config_path):
        click.echo('⚙ Creating config')
        click.echo()
        config['github'] = {'access_token': ''}
        os.mkdir(xdg_config_home() / 'shred-project-helper')
        with open(config_path, 'w+') as config_file:
            config.write(config_file)
    else:
        config.read(config_path)

    return (config, config_path)

def configSaveToken(config, path, github_token):
    save_token = click.confirm('Save access token to config?')
    if save_token:
        config['github']['access_token'] = github_token
        with open(path, 'w+') as config_file:
            config.write(config_file)

