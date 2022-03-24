import pandas as pd
from pathlib import Path
import numpy as np

def parse_one_aggregate_profile(csv_file=None, example=False, nrows=55, skiprows=3):
    """
    Takes a csv generated by nvprof with aggregate mode on, and returns a pandas series where the
    axis labels are the gpu activity/api call name and the metrics associated with it (aggregate time,
    percent time, # of calls, avg time, min time, max time).

    :param csv_file: the csv file
    :param example: boolean to use an example profile.  If true, csv_file is not needed.
    :param nrows: number of rows in the csv, for aggregate profiles, default is 55
    :param skiprows: number of rows to skip at the beginning of the csv, for aggregate profiles, default 3
    :return: a pandas series
    """

    if example:
        csv_file = Path.cwd() / "debug_profiles" / "resnet" / "resnet750691.csv"
    elif not csv_file:
        raise ValueError("csv_file must be provided if example is false.")

    if not csv_file.exists():
        raise ValueError(f"File {csv_file} does not exist")

    gpu_columns={
        "Type": "type",
        "Time": "time_ms",
        "Time(%)": "time_percent",
        "Calls": "num_calls",
        "Avg": "avg_us",
        "Min": "min_us",
        "Max": "max_ms",
        "Name": "name"
    }

    gpu_prof = pd.read_csv(csv_file, header=0, skiprows=skiprows, skip_blank_lines=True, nrows=nrows)
    gpu_prof = gpu_prof.rename(columns=gpu_columns)
    gpu_prof = gpu_prof.drop(0)

    attribute_cols = ["time_percent", "time_ms", "num_calls", "avg_us", "min_us", "max_ms"]

    result = gpu_prof.apply(
        lambda row: retrieve_row_attrs(row, name_col="name", attribute_cols=attribute_cols),
        axis=1
    )    # results in sparse dataframe
    result = result.backfill()      # put all of the information in the first row

    return result.iloc[0]


def retrieve_row_attrs(row, name_col, attribute_cols):
    """
    Takes 1 row of the gpu attributes such as

    type            time_percent    time_ms     num_calls   avg_us  min_us  max_ms      name
    GPU activities	88.005407	    38.058423	125	        304.467	0.864	13.759156	[CUDA memcpy HtoD]

    and returns a new Series with columns corresponding to the name.

    Example: calling this function on the row above with

    attribute_cols = ["time_percent", "time_ms", "num_calls", "avg_us", "min_us", "max_ms"]
    and
    name_col = "name"
    yeilds

    time_percent_[CUDA memcpy HtoD]     time_ms_[CUDA memcpy HtoD]  ... max_ms_[CUDA memcpy HtoD]
    88.005407                           38.058423                   ... 13.759156
    """

    return pd.Series({f"{attribute}_{row[name_col]}": float(row[attribute]) for attribute in attribute_cols})


def parse_one_system_profile(csv_file=None, example=False, nrows=5, skiprows=61, gpu=0):

    """
    Takes a csv generated by nvprof with aggregate mode on, and returns a pandas series where the
    axis labels are the system signals (clock, memory clock, temp, power, and fan) and the metrics
    associated with it (avg, min, max).

    :param csv_file: the csv file
    :param example: boolean to use an example profile.  If true, csv_file is not needed.
    :param nrows: number of rows in the csv, for aggregate profiles, default is 5
    :param skiprows: number of rows to skip at the beginning of the csv, for aggregate profiles, default 61
                    because the gpu profile activity comes in the first 61 rows
    :param gpu: the number of the gpu used for profiling (nvprof automatically collects system information
                on all gpus in the system)
    :return: a pandas series
    """

    if example:
        csv_file = Path.cwd() / "debug_profiles" / "resnet" / "resnet750691.csv"
    elif not csv_file:
        raise ValueError("csv_file must be provided if example is false.")

    if not csv_file.exists():
        raise ValueError(f"File {csv_file} does not exist")

    system_columns = {
        "Device": "device",
        "Count": "count",
        "Avg": "avg",
        "Min": "min",
        "Max": "max",
        "Unnamed: 0": "signal"
    }

    system_prof = pd.read_csv(csv_file, header=0, skiprows=skiprows, skip_blank_lines=True, nrows=nrows*(gpu+1))
    system_prof = system_prof.rename(columns=system_columns)
    system_prof["signal"] = system_prof["signal"].apply(
        lambda x: x.lower().replace(" ", "_")
    )   # format signal names

    if gpu > 0:
        # drop rows for other gpus
        system_prof = system_prof.drop(list(range(gpu*5)))

    attribute_cols = ["avg", "min", "max"]

    result = system_prof.apply(
        lambda row: retrieve_row_attrs(row, name_col="signal", attribute_cols=attribute_cols),
        axis=1
    )    # results in sparse dataframe
    result = result.backfill()      # put all of the information in the first row
    return result.iloc[0]


def parse_one_profile(csv_file=None, example=False, gpu=0):
    """
    Parse the gpu attributes and system attributes from a csv file from nvprof and return a pandas Series.

    :param csv_file: the csv filename.
    :param example: boolean indicating whether or not to use an example profile.  If true, csv_file is ignored.
    :param gpu: the gpu that the profile was run on.
    :return: a pandas Series
    """
    gpu_prof = parse_one_aggregate_profile(csv_file, example=example)
    system_prof = parse_one_system_profile(csv_file, example=example, gpu=gpu)
    return gpu_prof.append(system_prof)


def parse_all_profiles(folder="profiles", save_filename=None, gpu=0):
    """
    Parses all of the profiles under the folder into one dataframe saved as a csv in the folder.

    The folder, under cwd/profiles, is organized by subfolder according to model architecture.
    Model architecture and the filename are added as columns to the csv.

    :param folder: the folder containing subfolders by model architecture, which contain profiles,
                        such as ./profiles/<folder>/resnet/resnet12345.csv
    :param save_filename: the filename of the combined csv to save.
    :param gpu: the gpu that the profile was run on.
    :return: None, just saves a csv file.
    """
    root_folder = Path.cwd() / "profiles" / folder
    if not root_folder.exists():
        raise FileNotFoundError(f"Folder {root_folder} does not exist.")

    combined = pd.DataFrame()

    for subdir in [x for x in root_folder.iterdir() if x.is_dir()]:
        model = subdir.name
        for csv_profile in [x for x in subdir.iterdir()]:
            file = csv_profile.name
            prof = parse_one_profile(csv_file=csv_profile, gpu=gpu)
            prof = pd.Series({"file" : file, "model": model}).append(prof)
            combined = combined.append(prof, ignore_index=True)

    if save_filename is None:
        save_filename = "aggregated.csv"

    save_path = root_folder / save_filename
    combined.to_csv(save_path, index=False)
    return

a = parse_all_profiles("debug_profiles")