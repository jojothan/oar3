# -*- coding: utf-8 -*-
import datetime
import re
import sys
from json import dumps
from typing import Generator, List

import click

import oar.lib.tools as tools
from oar import VERSION
from oar.lib import db
from oar.lib.accounting import (
    get_accounting_summary,
    get_accounting_summary_byproject,
    get_last_project_karma,
)
from oar.lib.event import get_jobs_events
from oar.lib.job_handling import (
    get_array_job_ids,
    get_job_cpuset_name,
    get_job_resources_properties,
    get_jobs_state,
)
from oar.lib.tools import (
    check_resource_system_property,
    get_duration,
    local_to_sql,
    sql_to_local,
)

from .utils import CommandReturns

click.disable_unicode_literals_warning = True

STATE2CHAR = {
    "Waiting": "W",
    "toLaunch": "L",
    "Launching": "L",
    "Hold": "H",
    "Running": "R",
    "Terminated": "T",
    "Error": "E",
    "toError": "E",
    "Finishing": "F",
    "Suspended": "S",
    "Resuming": "S",
    "toAckReservation": "W",
    "NA": "-",
}


def get_table_lines(jobs) -> List[str]:
    # The headers to print
    headers: List[str] = [
        "Job id",
        "State",
        "User",
        "Duration",
        "System message",
    ]
    # First yield the headers
    yield headers

    now = tools.get_date()
    for job in jobs:
        # Compute job duration
        duration = 0
        if job.start_time:
            if now > job.start_time:
                if job.state in ["Running", "Launching", "Finishing"]:
                    duration = now - job.start_time
                elif job.stop_time != 0:
                    duration = job.stop_time - job.start_time
                else:
                    duration = -1

        # !! It must be consistent wih `header_columns`
        job_line = [
            str(job.id),
            STATE2CHAR[job.state],
            str(job.user),
            str(datetime.timedelta(seconds=duration)),
            str(job.message),
        ]

        yield job_line


def gather_all_user_accounting(items) -> List[str]:
    # The headers to print
    headers: List[str] = [
        "User",
        "First window starts",
        "Last window ends",
        "Asked (seconds)",
        "Used (seconds)",
    ]
    # First yield the headers
    yield headers

    for user, consumption_user in items:
        asked = 0
        if "ASKED" in consumption_user:
            asked = consumption_user["ASKED"]
        used = 0
        if "USED" in consumption_user:
            used = consumption_user["USED"]

        begin = local_to_sql(consumption_user["begin"])
        end = local_to_sql(consumption_user["end"])

        yield [
            user,
            str(begin),
            str(end),
            str(asked),
            str(used),
        ]


def print_table(
    objects: List[any],
    gather_prop: Generator[List[str], None, None],
    min_column_size: int = 7,
):
    """
    Simple algorithm to print a list of list given by a generator. Used to print the table of jobs in the terminal.
    It doesn't take into account the size of the terminal.

    Steps:
    - Construct a list of all lines List[List[str]] (where a list is a list of strings)
    - Gather all information about the jobs
    - For each column of each line find the longest string (that should be the size of the column)
    - Print every lines knowing the size of each columns
    """

    lines_generator = gather_prop(objects)

    # The first yielded value should be the header list
    lines = [next(lines_generator)]

    # List for the max size of each columns
    sizes = [len(i) if len(i) > min_column_size else min_column_size for i in lines[0]]

    # Loop through the job lines
    for line in lines_generator:
        for i in range(len(line)):
            if sizes[i] < len(line[i]):
                sizes[i] = len(line[i])

        lines.append(line)

    # Add a line of separators
    separators: List[str] = list(map(lambda size: "{}".format(size * "-"), sizes))
    # Insert it just after the headers
    lines.insert(1, separators)

    for line in lines:
        for col_idx in range(len(line)):
            col_size = sizes[col_idx]
            print(f"{{:^{col_size}s}} ".format(line[col_idx]), end="")
        print()


def print_jobs(legacy, jobs, json=False):
    if legacy and not json:
        print_table(jobs, get_table_lines)
    elif json:
        # TODO to enhance
        to_dump = {}
        # to_dict() doesn't incorporate attributes not defined in the , thus the dict merging
        jobs_properties = [
            {**j.to_dict(), **{"cpuset_name": j.cpuset_name}} for j in jobs
        ]
        for job in jobs_properties:
            to_dump[job["id"]] = job
        print(dumps(to_dump))
    else:
        print(jobs)


def print_accounting(cmd_ret, accounting, user, sql_property, json=False):
    # --accounting "YYYY-MM-DD, YYYY-MM-DD"
    m = re.match(
        r"\s*(\d{4}\-\d{1,2}\-\d{1,2})\s*,\s*(\d{4}\-\d{1,2}\-\d{1,2})\s*", accounting
    )
    if m:
        date1 = m.group(1) + " 00:00:00"
        date2 = m.group(2) + " 00:00:00"
        d1_local = sql_to_local(date1)
        d2_local = sql_to_local(date2)

        consumptions = get_accounting_summary(d1_local, d2_local, user, sql_property)
        # import pdb; pdb.set_trace()
        # One user output
        if user:
            asked = 0
            if user in consumptions and "ASKED" in consumptions[user]:
                asked = consumptions[user]["ASKED"]
            used = 0
            if user in consumptions and "USED" in consumptions[user]:
                used = consumptions[user]["USED"]

            print("Usage summary for user {} from {} to {}:".format(user, date1, date2))
            print("-------------------------------------------------------------")

            start_first_window = "No window found"
            if "begin" in consumptions[user]:
                start_first_window = local_to_sql(consumptions[user]["begin"])
            print("{:>28}: {}".format("Start of the first window", start_first_window))

            end_last_window = "No window found"
            if "end" in consumptions[user]:
                end_last_window = local_to_sql(consumptions[user]["end"])
            print("{:>28}: {}".format("End of the last window", end_last_window))

            print(
                "{:>28}: {:>10} ({:>10})".format(
                    "Asked consumption", asked, get_duration(asked)
                )
            )
            print(
                "{:>28}: {:>10} ({:>10})".format(
                    "Used consumption", used, get_duration(used)
                )
            )

            print("By project consumption:")

            consumptions_by_project = get_accounting_summary_byproject(
                d1_local, d2_local, user
            )
            for project, consumptions_proj in consumptions_by_project.items():
                print("  " + project + ":")
                asked = 0
                if "ASKED" in consumptions_proj and user in consumptions_proj["ASKED"]:
                    asked = consumptions_proj["ASKED"][user]
                used = 0
                if "USED" in consumptions_proj and user in consumptions_proj["USED"]:
                    used = consumptions_proj["USED"][user]

                print(
                    "{:>28}: {:>10} ({:>10})".format(
                        "Asked consumption", asked, get_duration(asked)
                    )
                )
                print(
                    "{:>28}: {:>10} ({:>10})".format(
                        "Used consumption", used, get_duration(used)
                    )
                )

                last_karma = get_last_project_karma(user, project, d2_local)
                if last_karma:
                    m = re.match(r".*Karma\s*\=\s*(\d+\.\d+)", last_karma)
                    if m:
                        print("{:>28}: {}".format("Last Karma", m.group(1)))
        # All users array output
        else:
            print_table(consumptions.items(), gather_all_user_accounting)
    else:
        cmd_ret.error("Bad syntax for --accounting", 1, 1)
        cmd_ret.exit()


def print_events(cmd_ret, job_ids, array_id, json=False):
    if array_id:
        job_ids = get_array_job_ids(array_id)

    if job_ids:
        events = get_jobs_events(job_ids)

        if not json:

            def gather_events(events):
                yield ["Date", "job id", "Type", "Description"]
                for event in events:
                    yield [
                        str(local_to_sql(event.date)),
                        str(event.job_id),
                        str(event.type),
                        str(event.description),
                    ]

            print_table(events, gather_events)
        else:
            events_per_jobs = dict()
            for event in events:
                if str(event.job_id) not in events_per_jobs:
                    events_per_jobs[str(event.job_id)] = []
                event_dict = {
                    "date": str(local_to_sql(event.date)),
                    "type": str(event.type),
                    "description": str(event.description),
                }
                events_per_jobs[str(event.job_id)].append(event_dict)
            print(dumps(events_per_jobs))

    else:
        cmd_ret.warning("No job ids specified")


def print_properties(cmd_ret, job_ids, array_id, json=False):
    if array_id:
        job_ids = get_array_job_ids(array_id)

    if job_ids:
        # Gather a list of [(Resource, job_id), ...]
        resources_properties = [
            (p, job_id)
            for job_id in job_ids
            for p in get_job_resources_properties(job_id)
        ]

        # For each job, construct the list of its resources properties
        properties_for_job = dict()
        for resource_properties, job_id in resources_properties:
            if job_id not in properties_for_job:
                properties_for_job[job_id] = []

            properties_for_job[job_id].append(
                {
                    prop: value
                    for prop, value in resource_properties.to_dict().items()
                    if not check_resource_system_property(prop)
                }
            )

        # If json, the `properties_for_job` is ready to be dumped
        if json:
            print(dumps(properties_for_job))
        else:
            # For normal print, all resources are printed in a new line regardless of their jobs
            # First flatten the properties into an array
            all_jobs = [
                properties
                for job_id, resources_properties in properties_for_job.items()  # Higher loop
                for properties in resources_properties  # Sublist
            ]
            for properties in all_jobs:
                property_line = ", ".join(
                    map(
                        lambda item: "{} = '{}'".format(item[0], item[1]),
                        properties.items(),
                    )
                )
                print(property_line)

    else:
        cmd_ret.warning("No job ids specified")


def print_state(cmd_ret, job_ids, array_id, json):
    # TODO json mode
    if array_id:
        job_ids = get_array_job_ids(array_id)
    if job_ids:
        job_ids_state = get_jobs_state(job_ids)
        if json:
            json_dict = {}
            for i, job_id_state in enumerate(job_ids_state):
                job_id, state = job_id_state
                json_dict[str(job_id)] = state
                # print('"{}" : "{}"{}'.format(job_id, state, comma))
            # import pdb; pdb.set_trace()
            print(dumps(json_dict))
        else:
            for job_id_state in get_jobs_state(job_ids):
                job_id, state = job_id_state
                print("{}: {}".format(job_id, state))
    else:
        cmd_ret.warning("No job ids specified")


def user_option_flag_or_string():
    """Click seems unable to manage option which is of type flag or string, _this_user_ is added to
    sys.argv when --user is used as flag , by example:
      -u --accounting "1970-01-01, 1970-01-20" -> -u _this_user_ --accounting "1970-01-01, 1970-01-20"
    """
    argv = []
    for i in range(len(sys.argv) - 1):
        a = sys.argv[i]
        argv.append(a)
        if (a == "-u" or a == "--user") and ((sys.argv[i + 1])[0] == "-"):
            argv.append("_this_user_")

    argv.append(sys.argv[-1])
    if (sys.argv[-1] == "-u") or (sys.argv[-1] == "--user"):
        argv.append("_this_user_")

    sys.argv = argv
    # print(sys.argv)


class UserOption(click.Command):
    def __init__(self, name, callback, params, help):
        user_option_flag_or_string()
        click.Command.__init__(self, name=name, callback=callback, params=params)


@click.command(cls=UserOption)
@click.option(
    "-j",
    "--job",
    type=click.INT,
    multiple=True,
    help="show information only for the specified job(s)",
)
@click.option("-f", "--full", is_flag=True, help="show full information")
@click.option("-s", "--state", is_flag=True, help="show only the state of a jobs.")
@click.option(
    "-u", "--user", type=click.STRING, help="show information for this user only"
)
@click.option(
    "-a",
    "--array",
    type=int,
    help="show information for the specified array_job(s) and toggle array view in",
)
@click.option(
    "-c", "--compact", is_flag=True, help="prints a single line for array jobs"
)
@click.option(
    "-g",
    "--gantt",
    type=click.STRING,
    help='show job information between two date-times "YYYY-MM-DD hh:mm:ss, YYYY-MM-DD hh:mm:ss"',
)
@click.option("-e", "--events", is_flag=True, type=click.STRING, help="show job events")
@click.option("-p", "--properties", is_flag=True, help="show job properties")
@click.option(
    "-A",
    "--accounting",
    type=click.STRING,
    help="show accounting information between two dates",
)
@click.option(
    "-S",
    "--sql",
    type=click.STRING,
    help="restricts display by applying the SQL where clause on the table jobs (ex: \"project = 'p1'\")",
)
@click.option(
    "-F",
    "--format",
    type=int,
    help="select the text output format. Available values 1 an 2",
)
@click.option("-J", "--json", is_flag=True, help="print result in JSON format")
@click.option("-V", "--version", is_flag=True, help="print OAR version number")
def cli(
    job,
    full,
    state,
    user,
    array,
    compact,
    gantt,
    events,
    properties,
    accounting,
    sql,
    format,
    json,
    version,
):
    """Print job information."""
    job_ids = job
    array_id = array

    start_time = None
    stop_time = None
    if gantt:  # --gantt "YYYY-MM-DD hh:mm:ss, YYYY-MM-DD hh:mm:ss"
        m = re.match(
            r"\s*(\d{4}\-\d{1,2}\-\d{1,2})\s+(\d{1,2}:\d{1,2}:\d{1,2})\s*,\s*(\d{4}\-\d{1,2}\-\d{1,2})\s+(\d{1,2}:\d{1,2}:\d{1,2})\s*",
            gantt,
        )
        date1 = m.group(1) + " " + m.group(2)
        date2 = m.group(3) + " " + m.group(4)
        start_time = sql_to_local(date1)
        stop_time = sql_to_local(date2)

    cmd_ret = CommandReturns(cli)
    # Print OAR version and exit
    if version:
        cmd_ret.print_("OAR version : " + VERSION)
        cmd_ret.exit()

    if user == "_this_user_":
        user = tools.get_username()

    if job_ids and array_id:
        cmd_ret.error(
            "Conflicting Job IDs and Array IDs (--array and -j cannot be used together)",
            1,
            1,
        )
        cmd_ret.exit()

    jobs = None
    if not accounting and not events and not state:
        jobs = db.queries.get_jobs_for_user(
            user, start_time, stop_time, None, job_ids, array_id, sql, detailed=full
        ).all()

        for job in jobs:
            job.cpuset_name = get_job_cpuset_name(job.id, job=job)

    if accounting:
        print_accounting(cmd_ret, accounting, user, sql)
    elif events:
        print_events(cmd_ret, job_ids, array_id, json=json)
    elif properties:
        print_properties(cmd_ret, job_ids, array_id, json=json)
    elif state:
        print_state(cmd_ret, job_ids, array_id, json)
    else:
        if jobs:
            print_jobs(True, jobs, json)

    cmd_ret.exit()
