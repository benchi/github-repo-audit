#!/usr/bin/env python
import os
import re
from collections import defaultdict
from datetime import timedelta, datetime

import click
from github import Github


JIRA_REGEX = r'([a-zA-Z]{3,4})[- ](\d{1,6})[ |,-_].*'


def make_maps(commits):
    jira_map = defaultdict(list)
    committer_map = defaultdict(list)
    for commit in commits:
        jira_map[jira_from_commit(commit)].append(commit)
        committer_map[committer_from_commit(commit)].append(commit)

    return jira_map, committer_map


def has_matching_files(commit, path, exclude_path):
    included = not path or any([f.filename.startswith(path) for f in commit.files])
    excluded = exclude_path and all([f.filename.startswith(exclude_path) for f in commit.files])

    return included and not excluded


def get_commits(github_client, repo, path='', lookback_days=90, exclude_path=''):
    ninety_days_ago = datetime.now() - timedelta(days=lookback_days)
    commits = github_client.search_commits('repo:%s author-date:>%s' % (repo, ninety_days_ago.strftime('%Y-%m-%d')))

    return [commit for commit in commits if has_matching_files(commit, path, exclude_path)]


def jira_from_commit(commit):
    commit_message = commit.raw_data['commit']['message']
    matches = re.search(JIRA_REGEX, commit_message)
    if matches:
        return matches.group(1).upper() + '-' + matches.group(2)
    else:
        return 'Unknown'


def committer_from_commit(commit):
    return '%s - %s' % (commit.author.login, commit.author.name)


def output_jira(jira, commits):
    authors = ', '.join([committer_from_commit(commit) for commit in commits])
    print('Uncovered JIRA: %s contributed by: %s' % (jira, authors))


def output_nontester(author, commits):
    jiras = ', '.join([jira_from_commit(commit) for commit in commits])
    print('Author did not write tests: %s. JIRAs: %s' % (author, jiras))


def output_pure_tester(author, commits):
    print('Author only wrote tests: %s' % (author))


@click.command()
@click.option('--prod_repo', '-pr', type=str, help='Production code repo')
@click.option('--prod_path', '-pp', type=str, default='', help='Production code path')
@click.option('--prod_exclude_path', '-pe', type=str, default='', help='Production code exclusion path')
@click.option('--test_repo', '-tr', type=str, default=None, help='Test code repo (Default same as prod)')
@click.option('--test_path', '-tp', type=str, default='', help='Test code path')
@click.option('--lookback', '-l', type=int, default=90, help='Lookback (in days - default 90)')
@click.option('--github_token', '-gt', type=str, default=None, help='Github token (default env var GITHUB_ACCESS_TOKEN)')
@click.option('--github_url', '-g', type=str, default='github.com', help='Github hostname (default github.com)')
def cli(prod_repo, prod_path, prod_exclude_path, test_repo, test_path, lookback, github_token, github_url):
    test_repo = test_repo or prod_repo
    github_token = github_token or os.environ['GITHUB_ACCESS_TOKEN']

    g = Github(base_url="https://%s/api/v3" % github_url, login_or_token=github_token)

    prod_commits = get_commits(g, prod_repo, prod_path, lookback, prod_exclude_path)
    test_commits = get_commits(g, test_repo, test_path, lookback)

    prod_jira_map, prod_committer_map = make_maps(prod_commits)
    test_jira_map, test_committer_map = make_maps(test_commits)

    uncovered_jiras = set(prod_jira_map.keys()) - set(test_jira_map.keys())
    non_testers = set(prod_committer_map.keys()) - set(test_committer_map.keys())
    pure_testers = set(test_committer_map.keys()) - set(prod_committer_map.keys())

    print ' --------------------------------- '
    for jira in uncovered_jiras:
        output_jira(jira, prod_jira_map[jira])

    print ' --------------------------------- '
    for author in non_testers:
        output_nontester(author, prod_committer_map[author])

    print ' --------------------------------- '
    for author in pure_testers:
        output_pure_tester(author, test_committer_map[author])


if __name__ == '__main__':
    try:
        cli()
    except Exception as e:
        print e
