#!/usr/bin/env python3
import os, pycurl, json, io, yaml, subprocess
from tqdm import tqdm

#CAMPAIGN = "RunIISummer20UL17"
#CAMPAIGN = "Run3Summer23"
CAMPAIGN = "RunIII2024Summer24"

CMSSW_VERSION = "CMSSW_15_0_2"
DATATIER = "MINIAODSIM"
#DAS_QUERY = f"/*/*{CAMPAIGN}*/{DATATIER}"
DAS_QUERY = "/DYto2E_MLL-50to120_TuneCP5_13p6TeV_powheg-pythia8/Run3Summer22MiniAODv3-124X_mcRun3_2022_realistic_v12-v2/MINIAODSIM"


def clean_up_cache(cache_files=['datasets.yaml', 'executable/', 'condor/', 'json/']):
    for cache in cache_files:
        os.system(f'rm -rf {cache}')


def inquire_datasets_from_DAS(outname='datasets', query=DAS_QUERY):
    # os.system(f"voms-proxy-init -voms cms -valid 192:0")
    print(f"Inquiring datasets matching {query}")
    os.system(f"/cvmfs/cms.cern.ch/common/dasgoclient --query=\"dataset dataset={query}\" --limit=-1 > {outname}.txt")
    with open(f'{outname}.txt', 'r', encoding='utf-8') as f:
        datasets = f.read().splitlines()
    os.system(f"rm -rf {outname}.txt")
    with open(f'{outname}.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(datasets, f)
    print(f"\tDone, stored in {outname}.yaml")
    return datasets


def check_XSDB_records(datasets: list, xsdb_url='https://xsecdb-xsdb-official.app.cern.ch'):
    recorded_datasets = []
    unrecorded_datasets = []

    # you can also create the cookie manually
    #os.remove(os.path.expanduser("~/private/xsdbdev-cookie.txt"))
    #os.system(f"auth-get-sso-cookie -u https://xsecdb-xsdb-official.app.cern.ch -o ~/private/xsdbdev-cookie.txt")

    c = pycurl.Curl()
    c.setopt(c.FOLLOWLOCATION, 1)
    c.setopt(c.COOKIEJAR, os.path.expanduser("~/private/xsdbdev-cookie.txt"))
    c.setopt(c.COOKIEFILE, os.path.expanduser("~/private/xsdbdev-cookie.txt"))
    c.setopt(c.HTTPHEADER, ['Content-Type:application/json', 'Accept:application/json'])
    c.setopt(c.VERBOSE, True)  # set to True for debug
    api_url = os.path.join(xsdb_url, 'api')
    c.setopt(c.URL, os.path.join(api_url, 'search'))
    c.setopt(c.POST, True)


    for dataset in tqdm(datasets, desc="Checking whether datasets recorded in XSDB or not"):
        process_name, campaign, dataier = dataset.split('/')[1:]
        query = {
            'process_name': process_name,
            #'DAS': campaign,
        }
        json_query = json.dumps(query)

        c.setopt(c.POSTFIELDS, json_query)
        byte_io = io.BytesIO()
        c.setopt(c.WRITEFUNCTION, byte_io.write)
        c.perform()
        search_result = byte_io.getvalue().decode('UTF-8')

        if search_result == '[]':
            unrecorded_datasets.append(dataset)
        elif search_result == '{}':
            raise ValueError("HTTP connection ERROR! Please debug by setting c.setopt(c.VERBOSE, True)")
        else:
            recorded_datasets.append(dataset)
    
    return recorded_datasets, unrecorded_datasets


def generate_executable_scripts(datasets, maxEvents=1_000_000, outdir='./executable/'):
    os.makedirs(outdir, mode=0o755, exist_ok=True)
    if not os.path.exists('compute_cross_section.py'):
        os.system("wget https://raw.githubusercontent.com/cms-sw/genproductions/refs/heads/master/Utilities/calculateXSectionAndFilterEfficiency/compute_cross_section.py")

    for dataset in tqdm(datasets, desc="Creating executable scripts to compute cross sections"):
        process_name, campaign, dataier = dataset.split('/')[1:]
        command = f"python3 compute_cross_section.py -f {dataset} -c {campaign} -n {maxEvents} -d {dataier} --skipexisting \"True\""
        output = subprocess.check_output(command, shell=True, text=True)
        script_path = os.path.join(outdir, f"{process_name}.sh")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join([
                "#!/usr/bin/env bash",
                "source /cvmfs/cms.cern.ch/cmsset_default.sh",
                f"cmsrel {CMSSW_VERSION}; cd {CMSSW_VERSION}/src; eval `scramv1 runtime -sh`; cd -",
                output,
                f"echo Done: {dataset}",
            ]))
        os.system(f"chmod +x {script_path}")


if __name__ == "__main__":
    clean_up_cache()
    datasets = inquire_datasets_from_DAS()

    recorded_datasets, unrecorded_datasets= check_XSDB_records(datasets=datasets)
    with open('datasets.yaml', 'w', encoding='utf-8') as f:
        yaml.dump({'unrecorded': unrecorded_datasets, 'recorded': recorded_datasets}, f)

    generate_executable_scripts(datasets=unrecorded_datasets)

