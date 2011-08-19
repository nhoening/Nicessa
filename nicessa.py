#!/usr/bin/python
# -*- coding:iso-8859-1

"""
This module contains the utility functions for the main use cases:
  * run simulations (locally or on some remote hosts via ssh access),
  * get data from hosts
  * generate plots
  * run T-tests
  * list runs made so far

The functions all expect the name of the simulation folder which should have an simulation.conf file in it.
A simulation folder will in the end contain the following dirs:

  * conf (configurations for batches of needed computations)
  * data (all log files)
  * plots (generated PDFs)

This module is careful with imports since it might be used in another context (on a remote host) and if
no remote support is needed, the user doesn't need paramiko
"""

'''
Copyright (c) 2011 Nicolas H�ning

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
'''

import os
import os.path as osp
import sys
from shutil import rmtree
from ConfigParser import ConfigParser
from subprocess import Popen

from sim.net import starter


def run(simfolder):
    ''' The main function to start running simulations

        :param string simfolder: relative path to simfolder
        :returns: True if successful, False otherwise
    '''
    from sim import setup, utils

    print '*' * 80
    sim_name = utils.ensure_name(simfolder)
    print "Running simulation %s" % utils.get_pretty_simulation_name("%s/simulation.conf" % simfolder, sim_name)
    print '*' * 80
    print;

    if not osp.exists("%s/nicessa.conf" % simfolder):
        print "[Nicessa] %s/nicessa.conf does not exist!" % simfolder
        utils.usage()
        return False

    if utils.is_remote(simfolder) or utils.cpus_per_host(simfolder)[1] > 1:
        from sim.net import remote
        return remote.run_remotely(simfolder, utils.get_main_conf(simfolder))
    else:
        return starter.batch(simfolder, 1, 1)


def run_more(simfolder):
    """ let the user make more runs on current config, in addition to the given data

        :param string simfolder: relative path to simfolder
        :returns: True if successful, False otherwise
    """
    from sim import utils
    simfolder = simfolder.strip('/')
    conf = utils.get_main_conf(simfolder)

    print "[Nicessa] Let's make %d more run(s)! Please tell me on which configurations.\n" % conf.getint('control', 'runs') \
          + "Enter any parameter values you want to narrow down to, nothing otherwise."

    sel_params = {}
    for o in conf.options('params'):
        selected = False
        print o
        params = [p.strip() for p in conf.get('params', o).split(',')]
        if len(params) <= 1:
            continue # no need to narrow down
        while not selected:
            print "%s ? (out of [%s])" % (o, conf.get('params', o))
            choice = []
            for selection in raw_input().split(','):
                selected = True
                if selection == "":
                    pass
                elif selection in params:
                    choice.append(selection)
                else:
                    print "Sorry, %s is not a valid value." % selection
                    selected = False
        if len(choice) > 0:
            sel_params[o] = choice
        else:
            print "No restriction chosen."
    print "You selected: %s. Do this? [Y|n]\n(Remember that configuration and code should still be the same!)" % str(sel_params)
    if raw_input().lower() in ["", "y"]:
        _prepare_dirs(simfolder, limit_to=sel_params, more=True)
        return run(simfolder)
    return False


def make_plots(simfolder, plot_nrs=[]):
    """ generate plots as specified in the simulation conf

        :param string simfolder: relative path to simfolder
        :param list plot_nrs: a list with plot indices. If empty, plot all there are.
    """
    from sim import utils
    from analysis import plotter

    simfolder = simfolder.strip('/')

    #if osp.exists("%s/plots" % simfolder):
    #   rmtree('%s/plots' % simfolder)
    if not osp.exists("%s/plots" % simfolder):
        os.mkdir('%s/plots' % simfolder)

    # tell about what we'll do if we have at least one plot
    relevant_confs = utils.get_relevant_confs(simfolder)
    for c in relevant_confs:
        if c.has_section("figure1"):
            print;
            print '*' * 80
            print "[Nicessa] creating plots ..."
            print '*' * 80
            print;
            break
    else:
        print "[Nicessa] No plots specified"

    # Describe all options first.
    # These might be set in plot-settings (in each simulation config) and per-figure
    general_options = {'use-colors':bool, 'use-tex':bool, 'line-width':int,\
                       'font-size':int, 'infobox-pos':str,\
                       'use-y-errorbars':bool, 'errorbar-every':int
                      }
    figure_specific_options = {
                       'name': str, 'xcol':int, 'x-range':str,\
                       'y-range':str, 'x-label': str, 'y-label': str,\
                       'custom-script':str
                      }
    figure_specific_options.update(general_options)

    def get_opt_val(conf, d, section, option, t):
        if conf.has_option(section, option):
            val = c.get(section, option).strip()
            if t is int:
                val = c.getint(section, option)
            if t is bool:
                val = c.getboolean(section, option)
            if t is float:
                val = c.getfloat(section, option)
            # config-options with '-' are nice, but not good parameter names
            d[option.replace('-', '_')] = val

    general_settings = {}
    c = ConfigParser(); c.read('%s/nicessa.conf' % (simfolder))
    for o,t in general_options.iteritems():
        get_opt_val(c, general_settings, 'plot-settings', o, t)
    general_params = []
    if c.has_option('plot-settings', 'params'):
        general_params = c.get('plot-settings', 'params').split(',')

    for c in relevant_confs:
        i = 1
        settings = general_settings.copy()
        # overwrite with plot-settings for this subsimulation
        for o, t in general_options.iteritems():
            get_opt_val(c, settings, 'plot-settings', o, t)
        if c.has_option('plot-settings', 'params'):
            general_params.extend(c.get('plot-settings', 'params').split(','))

        while c.has_section("figure%i" % i):
            if i in plot_nrs or len(plot_nrs) == 0:
                fig_settings = settings.copy()
                for o,t in figure_specific_options.iteritems():
                    get_opt_val(c, fig_settings, 'figure%i' % i, o, t)

                plot_confs = []
                j = 1
                while c.has_option("figure%i" % i, "plot%i" % j):
                    # make plot settings from conf string
                    d = utils.decode_search_from_confstr(
                            c.get('figure%i' % i, 'plot%i' % j),
                            sim = c.get('meta', 'name')
                        )
                    # then add general param settings to each plot, if
                    # not explicitly in there
                    for param in general_params:
                        if ":" in param:
                            param = param.split(':')
                            key = param[0].strip()
                            if not d.has_key(key):
                                d[key] = param[1].strip()
                    # making sure all necessary plot attributes are there
                    if d.has_key('_name') and d.has_key('_ycol') and d.has_key('_type'):
                        plot_confs.append(d)
                    else:
                        print '[NICESSA] Warning: Incomplete graph specification in Experiment %s - for plot %i in figure %i. '\
                              'Specify at least _name and _ycol.' % (c.get('meta', 'name'), j, i)
                    j += 1
                plotter.plot(filepath='%s/data' % simfolder,\
                             outfile_name='%s/plots/%s.pdf' \
                                % (simfolder, fig_settings['name']),\
                             plots=plot_confs,\
                             **fig_settings)
            i += 1


def run_ttests(simfolder):
    '''
    Make statistical t tests

    :param string simfolder: relative path to simfolder
    '''
    from analysis import harvester, tester
    relevant_confs = utils.get_relevant_confs(simfolder)

    # tell about what we'll do if we have at least one test
    for c in relevant_confs:
        if c.has_section("ttest1"):
            print;
            print '*' * 80
            print "[Nicessa] Running T-tests ..."
            print '*' * 80
            print;
            break
    else:
        print "[Nicessa] No T-tests specified"

    for c in relevant_confs:
        i = 1

        while c.has_section("ttest%i" % i):
            print "Test %s:" % c.get('ttest%i' % i,'name').strip('"')
            if not c.has_option("ttest%i" % i, "set1") or not c.has_option("ttest%i" % i, "set2"):
                print "[Nicessa] T-test %i is missing one or both data set descriptions." % i
                break

            tester.ttest(simfolder, c, i)
            i += 1


def list_data(simfolder):
    """ List the runs that have been made.

        :param string simfolder: relative path to simfolder
        :returns: True if successful, False otherwise
    """
    print "[Nicessa] The configurations and number of runs made so far:\n"
    for sim in utils.get_simulation_names(utils.get_main_conf(simfolder)):
        print "%s" % sim
        # get a list w/ relevant params
        cp = ConfigParser()
        simdirs = [d for d in os.listdir("%s/data" % simfolder) if d.startswith(sim)]
        if len(simdirs) == 0:
            print "No runs found for simulation %s\n" % sim
            continue
        onedir = "%s/data/%s" % (simfolder, simdirs[0])
        cp.read("%s/%s" % (onedir, [f for f in os.listdir(onedir) if f.endswith('.conf')][0]))
        params = cp.options('params')
        charlen = 1 + sum([len(p) + 6 for p in params]) + 9
        print '-' * charlen
        print "|",
        for p in params:
            print "  %s  |" % p ,
        print "| runs |"
        print '-' * charlen
        # now show how much we have in each relevant dir
        for dir in [d for d in os.listdir("%s/data" % simfolder) if d.startswith(sim)]:
            #print "%s | %d" % (d.ljust(70), utils.runs_in_folder(simfolder, d))
            cp = ConfigParser()
            path2dir = "%s/data/%s" % (simfolder, dir)
            cp.read("%s/%s" % (path2dir, [f for f in os.listdir(path2dir) if f.endswith('.conf')][0]))
            print "|",
            this_params = cp.options('params')
            for p in params:
                print "  %s|" % cp.get('params', p).ljust(len(p) + 2) ,
            print "| %s |" % str(utils.runs_in_folder(simfolder, dir)).rjust(4)
            print '-' * charlen
    return True

# ---------------------------------------------------------------------------------------------------

def _check_data(simfolder, more=False):
    """ check if old data is lyinf around, ask if it can go

        :param boolean more: when True, new data will simply be added to existing data
    """
    if osp.exists("%s/data" % simfolder) and len(os.listdir('%s/data' % simfolder)) > 0:
       if not more:
            print '[Nicessa] I found older log data (in %s/data). Remove? [y/N]' % simfolder
            if raw_input().lower() == 'y':
                rmtree('%s/data' % simfolder)


def _prepare_dirs(simfolder, limit_to={}, more=False):
    """ ensure that output directories exist, fill config directory with all subconfigs we want
        limit_to can contain parameter settings we want to limit ourselves to (this is in case we add more data)

        :param string simfolder: relative path to simfolder
        :param dict limit_to: key-value pairs that narrow down the dataset, when empty (default) all possible configs are run
        :param boolean more: when True, new data will simply be added to existing data
    """
    from sim import setup
    if not osp.exists("%s/data" % simfolder):
        os.mkdir('%s/data' % simfolder)
    if osp.exists("%s/conf" % simfolder):
        rmtree('%s/conf' % simfolder)

    conf = utils.get_main_conf(simfolder)
    setup.create(conf, simfolder, limit_to=limit_to, more=more)



if __name__ == "__main__":
    from sim import utils

    args = utils.read_args()

    utils.check_conf(args.folder)
    conf = utils.get_main_conf(args.folder)

    # if nothing special is selected, do standard program
    if args.run == args.results == args.check == args.ttests == args.more \
                == args.list and args.showscreen is None and args.plots is None:
        args.run = args.ttests = True
        args.plots = []
        if utils.is_remote(args.folder) or utils.cpus_per_host(args.folder)[1] > 1:
            args.results = True

    # 'first-class' commands : only one of these at a time:
    fine = True
    if args.more:
        fine = run_more(args.folder)
    elif args.run:
        if not utils.is_remote(args.folder):
            _check_data(args.folder, more=args.more)
        _prepare_dirs(args.folder)
        fine = run(args.folder)
    elif args.check:
        from sim.net import remote
        fine = remote.check(args.folder)
    elif args.showscreen:
        from sim.net import remote
        fine = remote.show_screen(args.folder, args.showscreen[0], args.showscreen[1])
    if args.list:
        fine = list_data(args.folder)

    if fine:
        if args.results:
            from sim.net import remote
            # create confs (again) so we know what we expect to find on which host
            if not args.run:
                _check_data(args.folder, more=args.more)
                _prepare_dirs(args.folder, more=args.more)
            remote.get_results(args.folder, do_wait=args.run)

        if args.plots is not None:
            make_plots(args.folder, plot_nrs=args.plots)

        if args.ttests:
            run_ttests(args.folder)


