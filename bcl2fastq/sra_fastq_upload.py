#!/usr/bin/env python3
"""Upload SRA request from Bcl2fastq pipeline
"""
# standard library imports
import os
import sys
import logging
import argparse
import json
import glob
import requests
import yaml

#--- project specific imports
#
# add lib dir for this pipeline installation to PYTHONPATH
LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)
from config import rest_services

__author__ = "Lavanya Veeravalli"
__email__ = "veeravallil@gis.a-star.edu.sg"
__copyright__ = "2016 Genome Institute of Singapore"
__license__ = "The MIT License (MIT)"


# global logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '[{asctime}] {levelname:8s} {filename} {message}', style='{'))
logger.addHandler(handler)

def main():
    """main function"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out_dir", required=True, help="out_dir")
    parser.add_argument("-m", "--mux_id", required=True, help="mux_id")
    parser.add_argument("-l", "--lib_id", help="lib_id")
    parser.add_argument('-t', "--test-server", action='store_true', help="Use STATS uploading to"\
        "test-server here and when calling bcl2fastq wrapper (-t)")
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="Increase verbosity")
    parser.add_argument('-q', '--quiet', action='count', default=0,
                        help="Decrease verbosity")
    args = parser.parse_args()
    # Repeateable -v and -q for setting logging level.
    # See https://www.reddit.com/r/Python/comments/3nctlm/what_python_tools_should_i_be_using_on_every/
    # and https://gist.github.com/andreas-wilm/b6031a84a33e652680d4
    # script -vv -> DEBUG
    # script -v -> INFO
    # script -> WARNING
    # script -q -> ERROR
    # script -qq -> CRITICAL
    # script -qqq -> no loggerging at all
    logger.setLevel(logging.WARN + 10*args.quiet - 10*args.verbose)

    if not os.path.exists(args.out_dir):
        logger.fatal("out_dir %s does not exist", args.out_dir)
        sys.exit(1)
    logger.info("out_dir is %s", args.out_dir)
    confinfo = os.path.join(args.out_dir + '/conf.yaml')
    if not os.path.exists(confinfo):
        logger.fatal("conf info '%s' does not exist under Run directory.\n", confinfo)
        sys.exit(1)
    if args.test_server:
        rest_url = rest_services['sra_upload']['testing']
        logger.info("send status to development server")
    else:
        rest_url = rest_services['sra_upload']['production']
        logger.info("send status to production server")
    email = "rpd@gis.a-star.edu.sg"
    if args.lib_id:
        lib_upload_status = False
    with open(confinfo) as fh_cfg:
        yaml_data = yaml.safe_load(fh_cfg)
        assert "run_num" in yaml_data
        run_num = yaml_data["run_num"]
        assert "units" in yaml_data
        if not "Project_"+args.mux_id in yaml_data["units"]:
            logger.fatal("mux_id %s does not exist in conf.yaml under %s", \
                args.mux_id, args.out_dir)
            sys.exit(1)
        for k, v in yaml_data["units"].items():
            if k == "Project_{}".format(args.mux_id):
                data = {}
                req = {}
                req_code = {}
                mux_dir = v.get('mux_dir')
                mux_id = v.get('mux_id')
                bcl_success = os.path.join(args.out_dir, "out", mux_dir, "bcl2fastq.SUCCESS")
                if os.path.exists(bcl_success):
                    logger.info("Bcl2fastq completed for %s hence Upload the STATs", mux_dir)
                    for child in os.listdir(os.path.join(args.out_dir, "out", mux_dir)):
                        if child.startswith('Sample'):
                            sample_path = os.path.join(args.out_dir, "out", mux_dir, child)
                            fastq_data = glob.glob(os.path.join(sample_path, "*fastq.gz"))
                            # if FASTQ data exists
                            if len(fastq_data) > 0:
                                libraryId = child.split('_')[-1]
                                if args.lib_id and args.lib_id != libraryId:
                                    continue
                                data['libraryId'] = libraryId
                                data['muxId'] = mux_id
                                data['runId'] = run_num
                                data['path'] = [sample_path]
                                data['email'] = [email]
                                req_code['reqCode'] = "SA-A002-009"
                                req_code['SA-A002-009'] = data
                                req['Request'] = req_code
                                test_json = json.dumps(req)
                                data_json = test_json.replace("\\", "")
                                headers = {'content-type': 'application/json'}
                                response = requests.post(rest_url, data=data_json, headers=headers)
                                print(response.status_code)
                                if response.status_code == requests.codes.ok:
                                    logger.info("Uploading %s completed successfully", \
                                        sample_path)
                                    logger.info("JSON request was %s", data_json)
                                    logger.info("Response was %s", response.status_code)
                                    if args.lib_id:
                                        lib_upload_status = True
                                else:
                                    logger.error("Uploading %s completed failed", sample_path)
                                    sys.exit(1)
                            else:
                                logger.error("There are no fastq file genereated for %s", \
                                    child)
                    if args.lib_id and not lib_upload_status:
                        logger.error("Libray %s data is not available. Please check the" \
                            " library name", args.lib_id)
                else:
                    logger.info("Bcl2fastq is not completed for %s", mux_dir)
                    sys.exit(1)

if __name__ == "__main__":
    logger.info("STATS update starting")
    main()
    logger.info("Successful program exit")
