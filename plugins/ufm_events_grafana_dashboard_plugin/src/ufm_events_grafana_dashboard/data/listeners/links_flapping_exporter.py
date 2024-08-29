#
# Copyright © 2013-2024 NVIDIA CORPORATION & AFFILIATES. ALL RIGHTS RESERVED.
#
# This software product is a proprietary product of Nvidia Corporation and its affiliates
# (the "Company") and all right, title, and interest in and to the software
# product, including all associated intellectual property rights, are and
# shall remain exclusively with the Company.
#
# This software product is governed by the End User License Agreement
# provided with the software product.
#

import csv
import time
import pandas as pd

from os import path
from io import StringIO
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta

from data.listeners.base_listener import BaseListener
from data.models.telemetry_metrics_model import TelemetryMetricsModel
from constants import DataType, LinkFlapping, Prometheus
from mgr.configurations_mgr import UFMEventsGrafanaConfigParser
from utils.netfix.links_flapping import get_links_flapping
from utils.logger import Logger
from prometheus.remote_write_utils import write_from_list_metrics_in_chunks


class LinksFlappingExporter(BaseListener):
    """
    Handles the export and monitoring of link flapping events.

    The LinksFlappingExporter class is responsible for triggering the
    retrieval of flapping links at specified intervals. It aggregates
    the results and stores them in a CSV file. Additionally, it updates
    a Prometheus counter to monitor link flapping events.
    """

    METADATA_KEYS = [
        LinkFlapping.LINK_ID,
        LinkFlapping.NODE_DESC,
        LinkFlapping.PARTNER_NODE_DESC
    ]

    def __init__(self, data_manager: 'Type[DataManager]'):
        super().__init__(data_manager, [DataType.TELEMETRY])
        conf: UFMEventsGrafanaConfigParser = UFMEventsGrafanaConfigParser.getInstance()
        ####
        self.duration: timedelta = timedelta(seconds=conf.get_links_flapping_interval_in_secs())
        self.report_output_path: str = path.join(conf.get_links_flapping_output_path(), 'links_flapping_report.csv')
        self.prometheus_ip = conf.get_prometheus_ip()
        self.prometheus_port = conf.get_prometheus_port()
        self.prometheus_max_chunk_size = conf.get_prometheus_request_max_chunk_size()
        ####
        self.last_csv_sample: str = ''
        self.link_flapping_dict = {}  # TODO:: if the csv file exists. initialize the dict should be from the file
        self.last_ts: Optional[datetime] = None

    def _append_link_flapping_to_dict(self, link: Dict):
        """
        Append or update a link flapping record in the link_flapping_dict.

        This function checks if a link flapping record already exists in the
        link_flapping_dict. If it does not exist, it creates a new entry with
        initial metadata and counters. If it exists, it updates the counter
        and the last time the flapping occurred.

        Args:
            link (Dict): A dictionary containing link flapping information.

        Returns:
            Dict: The updated or newly created dictionary entry for the link.
        """

        link_id: str = link.get(LinkFlapping.LINK_ID)
        link_dict = self.link_flapping_dict.get(link_id)
        if link_dict is None:
            link_dict = {key: link.get(key) for key in self.METADATA_KEYS}
            link_dict = {
                **link_dict,
                LinkFlapping.FIRST_TIME_OCCURRED: link.get(LinkFlapping.EXPECTED_TIME),
                LinkFlapping.LAST_TIME_OCCURRED: link.get(LinkFlapping.EXPECTED_TIME),
                LinkFlapping.LINK_FLAPPING_COUNTER: 1
            }
            self.link_flapping_dict[link_id] = link_dict
            return link_dict
        link_dict[LinkFlapping.LINK_FLAPPING_COUNTER] = link_dict.get(LinkFlapping.LINK_FLAPPING_COUNTER) + 1
        link_dict[LinkFlapping.LAST_TIME_OCCURRED] = link.get(LinkFlapping.EXPECTED_TIME)
        return link_dict

    def _process_prometheus_entry(self, link: Dict) -> Dict:
        """
        Convert a link flapping record into a Prometheus-compatible dictionary.

        This function processes a link flapping record by extracting the timestamp,
        converting it to milliseconds, and organizing the data into a dictionary
        format suitable for Prometheus metrics.

        Args:
            link (Dict): A dictionary containing link flapping information.

        Returns:
            Dict: A dictionary formatted for Prometheus metrics, including the timestamp,
                  labels, and counter value.
        """

        ts = datetime.strptime(link.get(LinkFlapping.LAST_TIME_OCCURRED), '%Y-%m-%d %H:%M:%S')
        ts_ms = int(ts.timestamp() * 1000)
        return {
            LinkFlapping.LINK_FLAPPING_COUNTER: {
                Prometheus.TIMESTAMP: ts_ms,
                Prometheus.LABELS: {
                    label: str(link.get(label)) for label in self.METADATA_KEYS
                },
                Prometheus.COUNTER_VALUE: link.get(LinkFlapping.LINK_FLAPPING_COUNTER)
            }
        }

    def _update_link_flapping_csv(self):
        """
        Update the CSV file with the current link flapping data.

        This function writes the contents of the link_flapping_dict to a CSV file
        specified by the report_output_path. It overwrites the existing file with
        the latest data, including a header row derived from the dictionary keys.
        """
        # Open the file in write mode
        csv_file = self.report_output_path
        with open(csv_file, 'w', newline='') as file:

            fieldnames = list(next(iter(self.link_flapping_dict.values())).keys())

            # Create a DictWriter object
            writer = csv.DictWriter(file, fieldnames=fieldnames)

            # Write the header
            writer.writeheader()

            # Write the data
            for _, row in self.link_flapping_dict.items():
                writer.writerow(row)

    def _process_link_flapping_records(self, data: List[Dict]):
        """
        Process new link flapping records/events.

        This function performs the following steps:
        1. Updates the records/counters to the link_flapping_dict.
        2. Exports link_flapping_dict to a CSV file.
        3. Writes the new counters to the Prometheus database.

        Args:
            data (List[Dict]): A list of dictionaries containing link flapping records.
        """
        metrics_list: List[Any] = []
        for link in data:
            link_dict: Dict = self._append_link_flapping_to_dict(link)
            metric_dict: Dict = self._process_prometheus_entry(link_dict)
            metrics_list.append(metric_dict)
        self._update_link_flapping_csv()
        write_from_list_metrics_in_chunks(metrics_data=metrics_list,
                                          target_id=self.prometheus_ip,
                                          target_port=self.prometheus_port,
                                          max_chunk_size=self.prometheus_max_chunk_size)

    def update_data(self):
        """
        update_data will be triggered each time new data arrives in TelemetryMetricsModel.
        This function will trigger links_flapping report
        if the time duration between the new data and the last triggering time is greater than self.duration
        """
        telemetry_model: TelemetryMetricsModel = self.data_manager.get_model_by_data_type(DataType.TELEMETRY)
        try:
            with telemetry_model.lock:
                new_csv_sample = telemetry_model.last_metrics_csv
                new_dt = datetime.fromtimestamp(telemetry_model.ts)
                if not self.last_csv_sample:
                    self.last_csv_sample = new_csv_sample
                    self.last_ts = new_dt
                    # no need in that case to trigger the links_flapping report
                    # since it requires two samples, and at the beginning we have only one sample
                    return
                # check if the time diff meets the duration
                time_diff: timedelta = new_dt - self.last_ts
                if time_diff >= self.duration:
                    Logger.log_message(f'Start the links flapping analysis report based for the last {self.duration}')
                    pst = time.time()
                    df: pd.DataFrame = get_links_flapping(
                        prev_counters_csv=StringIO(self.last_csv_sample),
                        cur_counters_csv=StringIO(new_csv_sample)
                    )
                    pet = time.time()
                    # get flapping links list
                    flapping_links_list: List[Dict] = df.to_dict(orient='records')
                    proc_time = round(pet - pst, 2)
                    Logger.log_message(f'The links flapping analysis report completed successfully in {proc_time}, '
                                       f'{len(flapping_links_list)} flapped links were found.')
                    # update the last_csv_sample & last_ts
                    self.last_csv_sample = new_csv_sample
                    self.last_ts = new_dt
                    # process the results
                    self._process_link_flapping_records(flapping_links_list)
        except Exception as ex:
            Logger.log_message(f'Failed to complete the links flapping analysis report: {str(ex)}')
