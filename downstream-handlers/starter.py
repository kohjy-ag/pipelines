#!/usr/bin/env python3
"""downstream jobs from pipeline_runs collection are satrted
"""
# standard library imports
import logging
import sys
import os
import argparse
import tempfile
import subprocess

#--- third party imports
#
import yaml

#--- project specific imports
#
# add lib dir for this pipeline installation to PYTHONPATH
LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)
from pipelines import generate_window, is_devel_version
from pipelines import get_downstream_outdir, is_production_user
from mongodb import mongodb_conn
path_devel = LIB_PATH + "/../"

__author__ = "Lavanya Veeravalli"
__email__ = "veeravallil@gis.a-star.edu.sg"
__copyright__ = "2016 Genome Institute of Singapore"
__license__ = "The MIT License (MIT)"

PRODUCTION_PIPELINE_VERSION = {
    'GIS': {
        'production': '/mnt/projects/rpd/pipelines/',
        'devel': path_devel},
    'NSCC': {
        'devel': '/home/users/astar/gis/gisshared/rpd/pipelines.git/',
        'production': '/home/users/astar/gis/gisshared/rpd/pipelines/'}
}

# global logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '[{asctime}] {levelname:8s} {filename} {message}', style='{'))
logger.addHandler(handler)

def start_analysis(record, testing, dry_run):
    """ Start the analysis
    """
    pipeline_params = " "
    extra_conf = " --extra-conf "
    extra_conf += "db-id:" + str(record['_id'])
    extra_conf += " requestor:" + record['requestor']
    outdir = get_downstream_outdir(record['requestor'], record['pipeline_name'], \
        record['pipeline_version'])
    # sample_cfg and references_cfg
    references_cfg = ""
    sample_cfg = ""
    for outer_key, outer_value in record.items():
        if outer_key == 'sample_cfg':
            logger.info("write temp sample_config")
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', prefix='sample_cfg_', \
                delete=False) as fh:
                sample_cfg = fh.name
                yaml.dump(outer_value, fh, default_flow_style=False)
        elif outer_key == 'references_cfg':
            logger.info("write temp reference_config")
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', prefix='references_cfg_', \
                delete=False) as fh:
                references_cfg = fh.name
                yaml.dump(outer_value, fh, default_flow_style=False)
        elif outer_key == 'cmdline':
            logger.info("pipeline_cmd")
            for key, value in outer_value.items():
                pipeline_params += " --" + key + " " + value
    #pipeline path for production and testing
    if testing:
        pipeline_version = ""
    else:
        pipeline_version = record['pipeline_version']
    pipeline_path = get_pipeline_path(record['site'], record['pipeline_name'], \
        pipeline_version)
    pipeline_script = os.path.join(pipeline_path, (os.path.split(pipeline_path)[-1] + ".py"))
    pipeline_cmd = pipeline_script + " --sample-cfg " + sample_cfg  + " -o " + outdir + " -n"
    if not sample_cfg:
        logger.critical("Job doesn't have sample_cfg %s", str(record['_id']))
        sys.exit(1)
    if references_cfg:
        ref_params = " --references-cfg " + references_cfg
        pipeline_cmd += ref_params
    if testing:
        pipeline_cmd += " --db-logging t"
    if pipeline_params:
        pipeline_cmd += pipeline_params
    if extra_conf:
        pipeline_cmd += extra_conf
    logger.info(pipeline_cmd)
    if dry_run:
        logger.info("Skipping dryrun option")
        return
    try:
        logger.info(pipeline_cmd)
        _ = subprocess.check_output(pipeline_cmd, stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        logger.fatal("The following command failed with return code %s: %s",
            e.returncode, ' '.join(pipeline_cmd))
        logger.fatal("Output: %s", e.output.decode())
def get_pipeline_path(site, pipeline_name, pipeline_version):
    """ get the pipeline path
    """
    basedir_map = PRODUCTION_PIPELINE_VERSION
    if site not in basedir_map:
        raise ValueError(site)
    if is_devel_version():
        basedir = basedir_map[site]['devel']
    else:
        basedir = basedir_map[site]['production']
    pipeline_path = os.path.join(basedir, pipeline_version, pipeline_name)
    return pipeline_path

def main():
    """main function
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-n', "--dry-run", action='store_true',
                        help="Don't run anything")
    parser.add_argument('-s', "--site",
                        help="site information")
    parser.add_argument('-t', "--testing", action='store_true',
                        help="Use MongoDB test-server here and when calling bcl2fastq wrapper (-t)")
    default = 14
    parser.add_argument('-w', '--win', type=int, default=default,
                        help="Number of days to look back (default {})".format(default))
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="Increase verbosity")
    parser.add_argument('-q', '--quiet', action='count', default=0,
                        help="Decrease verbosity")
    args = parser.parse_args()

    # Repeateable -v and -q for setting logging level.
    # See https://www.reddit.com/r/Python/comments/3nctlm/what_python_tools_should_i_be_using_on_every
    # and https://gist.github.com/andreas-wilm/b6031a84a33e652680d4
    # script -vv -> DEBUG
    # script -v -> INFO
    # script -> WARNING
    # script -q -> ERROR
    # script -qq -> CRITICAL
    # script -qqq -> no logging at all
    logger.setLevel(logging.WARN + 10*args.quiet - 10*args.verbose)
    if not is_production_user():
        logger.warning("Not a production user. Skipping MongoDB update")
        sys.exit(1)
    if not args.site:
        site = 'NSCC'
    else:
        site = args.site
    connection = mongodb_conn(args.testing)
    if connection is None:
        sys.exit(1)
    db = connection.gisds.pipeline_runs
    epoch_present, epoch_back = generate_window(args.win)
    results = db.find({"run" : {"$exists": False}, "site" : site,
        "ctime": {"$gt": epoch_back, "$lt": epoch_present}})
    logger.info("Found %s runs to start analysis", results.count())
    for record in results:
        start_analysis(record, args.testing, args.dry_run)

if __name__ == "__main__":
    main()
