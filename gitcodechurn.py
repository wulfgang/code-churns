"""
Author: Francis Lacle
License: MIT
Version: 0.1

Script to compute "true" code churn of a Git repository.

Code churn has several definitions, the one that to me provides the
most value as a metric is:

"Code churn is when an engineer
rewrites their own code in a short period of time."

Reference: https://blog.gitprime.com/why-code-churn-matters/

This script looks at a range of commits per author. For each commit it
book-keeps the files that were changed along with the lines of code (LOC)
for each file. LOC are kept in a sparse structure and changes per LOC are taken
into account as the program loops. When a change to the same LOC is detected it
updates this separately to bookkeep the true code churn.

Result is a print with aggregated contribution and churn per author for a
given time period.

Tested with Python version 3.5.3 and Git version 2.20.1

additions by gang.wang2:
1. search the dir to find out each author's contributions and churns, no need to specify the author
2. use pyecharts to visualize the contributions and churns

"""

import subprocess
import shlex
import os
import argparse
import datetime
import pdb
import pyecharts.options as opts
from pyecharts.charts import Bar, Line


def main():
    parser = argparse.ArgumentParser(
        description='Compute true git code churn (for project managers)'
    )
    parser.add_argument(
        '--before',
        type=str,
        help='before a certain date, in YYYY-MM-DD format'
    )
    parser.add_argument(
        '--after',
        type=str,
        help='after a certain date, in YYYY-MM-DD format'
    )
    '''
    parser.add_argument(
        '--author',
        type = str,
        help = 'author string (not committer)'
    )
    '''
    parser.add_argument(
        '--dir',
        type=str,
        help='Git repository directory'
    )
    parser.add_argument(
        '--gui',
        type=bool,
        help='if you want to have a visualized display'
    )
    args = parser.parse_args()

    before = args.before
    after = args.after
    # author = args.author
    directory = args.dir
    gui = args.gui
    project = directory[directory.rfind('/') + 1:]

    authors = {}  # a dictionary with key as name and value as email address
    authors = get_authors(directory)

    names = []  # authors.keys()  ## return a list of names
    contributions = []
    churns = []
    nets = []
    for author in authors:

        commits = get_commits(before, after, author, directory)

        # structured like this: files -> LOC
        files = {}

        contribution = 0
        churn = 0

        for commit in commits:
            [files, contribution, churn] = get_loc(
                commit,
                directory,
                files,
                contribution,
                churn
            )

        # print files in case more granular results are needed
        print('author: ', author)
        # print('files: ', files)
        print('contribution: ', contribution)
        print('churn: ', -churn)

        if contribution != 0 | churn != 0:  # zero impact will be removed from display
            names.append(author)
            contributions.append(contribution)
            churns.append(0 - churn)
        nets.append(contribution - churn)

    if gui:
        render(names, contributions, churns, nets, project)


def render(names, contributions, churns, nets, project):
    bar = Bar()
    bar.add_xaxis(names)
    bar.add_yaxis("contribution",
                  contributions,
                  stack="stack1",
                  category_gap="50%",
                  color="red",
                  label_opts=opts.LabelOpts(vertical_align='middle', position='top'))
    bar.add_yaxis("churn",
                  churns,
                  stack="stack1",
                  category_gap="50%",
                  color="green",
                  label_opts=opts.LabelOpts(vertical_align='middle', position='bottom'))
    bar.set_global_opts(
        datazoom_opts=[opts.DataZoomOpts(), opts.DataZoomOpts(type_="inside")],
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
        title_opts=opts.TitleOpts(title=project, subtitle=""),
        toolbox_opts=opts.ToolboxOpts()).render("codechurns.html")


'''
    line = (
        Line()
            .add_xaxis(xaxis_data=names)
            .add_yaxis(
            series_name="contributions",
            # yaxis_index=1,
            y_axis=nets
            # label_opts=opts.LabelOpts(is_show=False),
        )
    )

    bar.overlap(line).set_global_opts(
        toolbox_opts=opts.ToolboxOpts(),
        legend_opts=opts.LegendOpts(is_show=False),
    ).render("codechurns.html")
'''


def get_authors(dir):
    command = 'git log --pretty="%an <%ae>"'
    results = get_proc_out(command, dir).splitlines()
    res = list(set(results))  # remove duplications
    dict = {}
    for line in res:
        name = line[:line.find(' ')]
        dict[name] = line[line.find(' '):]
    return dict


def get_loc(commit, dir, files, contribution, churn):
    # git show automatically excludes binary file changes
    command = 'git show --format= --unified=0 --no-prefix ' + commit
    results = get_proc_out(command, dir).splitlines()
    file = ''
    loc_changes = ''
    # if commit == "bf19b330ba87c35c413920c7db38fb083e8f8252":
    #    pdb.set_trace()
    # loop through each row of output
    for result in results:
        new_file = is_new_file(result, file)
        if file != new_file:
            file = new_file
            if file not in files:
                files[file] = {}
        else:
            new_loc_changes = is_loc_change(result, loc_changes)
            if loc_changes != new_loc_changes:
                loc_changes = new_loc_changes
                locc = get_loc_change(loc_changes)
                # print(locc)
                for loc in locc:
                    if loc in files[file]:
                        files[file][loc] += locc[loc]
                        churn += abs(locc[loc])
                    else:
                        files[file][loc] = locc[loc]
                        contribution += abs(locc[loc])
            else:
                continue
    return [files, contribution, churn]


# arrives in a format such as -13 +27,5 (no decimals/commas == 1 loc change)
# returns a dictionary where left are removals and right are additions
# if the same line got changed we subtract removals from additions
def get_loc_change(loc_changes):
    # removals
    left = loc_changes[:loc_changes.find(' ')]
    left_dec = 0
    if left.find(',') > 0:
        comma = left.find(',')
        left_dec = int(left[comma + 1:])
        left = int(left[1:comma])
    else:
        left = int(left[1:])
        left_dec = 1

    # additions
    right = loc_changes[loc_changes.find(' ') + 1:]
    right_dec = 0
    if right.find(',') > 0:
        comma = right.find(',')
        right_dec = int(right[comma + 1:])
        right = int(right[1:comma])
    else:
        right = int(right[1:])
        right_dec = 1

    if left == right:
        return {left: (right_dec - left_dec)}
    else:
        return {left: left_dec, right: right_dec}


def is_loc_change(result, loc_changes):
    # search for loc changes (@@ ) and update loc_changes variable
    if result.startswith('@@'):
        loc_change = result[result.find(' ') + 1:]
        loc_change = loc_change[:loc_change.find(' @@')]
        return loc_change
    else:
        return loc_changes


def is_new_file(result, file):
    # search for destination file (+++ ) and update file variable
    if result.startswith('+++'):
        return result[result.rfind(' ') + 1:]
    else:
        return file


def get_commits(before, after, author, dir):
    # note --no-merges flag (usually we coders do not overhaul contributions)
    # note --reverse flag to traverse history from past to present
    command = 'git log --author="' + author + '" --format="%h" --no-abbrev '
    command += '--before="' + before + '" --after="' + after + '" --no-merges --reverse'
    return get_proc_out(command, dir).splitlines()


# not used but still could be of value in the future
def get_files(commit, dir):
    # this also works in case --no-merges flag is ommitted prior
    command = 'git show --numstat --pretty="" ' + commit
    results = get_proc_out(command, dir).splitlines()
    for i in range(len(results)):
        # remove the tabbed stats from --numstat
        results[i] = results[i][results[i].rfind('\t') + 1:]
    return (results)


def get_proc_out(command, dir):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=dir,
        shell=True
    )
    return process.communicate()[0].decode("utf-8")


if __name__ == '__main__':
    main()
