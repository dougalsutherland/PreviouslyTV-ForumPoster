from __future__ import print_function
import re
import socket
import traceback

from flask import abort, g, Response, request
from robobrowser import RoboBrowser

from ..app import app
from ..config.deploy import FORUM_USERNAME, FORUM_PASSWORD
from ..models import Mod, Report, Show, Turf, TURF_LOOKUP


BASE = 'http://forums.previously.tv'
REPORT_URL = re.compile(r'{}/modcp/reports/(\d+)/?$'.format(BASE))

import warnings
warnings.filterwarnings(
    'ignore', "No parser was explicitly specified", UserWarning)


def make_browser():
    return RoboBrowser(history=True)


def login(browser):
    browser.open('{}/login/'.format(BASE))
    form = browser.get_form(method='post')
    form['auth'] = FORUM_USERNAME
    form['password'] = FORUM_PASSWORD
    browser.submit_form(form)


def open_with_login(browser, url):
    browser.open(url)
    error_divs = browser.select('#elError')
    if error_divs:
        error_div, = error_divs
        msg = error_div.select_one('#elErrorMessage').text
        if "is not available for your account" in msg:
            login(browser)
            browser.open(url)


def get_reports(browser):
    # only gets from the first page, for now
    open_with_login(browser, '{}/modcp/reports/'.format(BASE))
    resp = []
    for a in browser.select('h4 a[href^={}/modcp/reports/]'.format(BASE)):
        if a.find_parent(class_='ipsDataItem_main').select('.fa-envelope'):
            continue  # skip reports of PMs
        report_id = int(REPORT_URL.match(a.attrs['href']).group(1))
        resp.append((a.text.strip(), report_id))
    return resp


def report_forum(report_id, browser):
    url = '{}/modcp/reports/{}/?action=find'.format(BASE, report_id)
    open_with_login(browser, url)
    sel = ".ipsBreadcrumb li[itemprop=itemListElement] a[href^={}/forum/]"
    for a in reversed(browser.select(sel.format(BASE))):
        try:
            return Show.get(Show.url == a.attrs['href'])
        except Show.DoesNotExist:
            pass

    msg = "No shows found for {}. Maybe a brand-new forum?"
    raise ValueError(msg.format(report_id))


def at_mention(user):
    return ('''<a contenteditable="false" data-ipshover="" '''
            '''data-ipshover-target="{u.profile_url}?do=hovercard" '''
            '''data-mentionid="{u.forum_id}" href="{u.profile_url}" '''
            '''rel="">@{u.name}</a>''').format(u=user)


def build_comment(report_id, show):
    turfs = show.turf_set.join(Mod).order_by(Mod.name)
    leads = [t.mod for t in turfs.where(Turf.state == TURF_LOOKUP['lead'])]
    backups = [t.mod for t in turfs.where(Turf.state == TURF_LOOKUP['backup'])]

    c = '<a href="{show.url}">{show.name}</a>'.format(show=show)

    if leads:
        c += ' leads: ' + ', '.join(at_mention(m) for m in leads) + '.'
        if backups:
            c += ' Backups: ' + ', '.join(m.name for m in backups) + '.'
    elif backups:
        c += ': No leads for this show.'
        c += ' Backups: ' + ', '.join(at_mention(m) for m in backups) + '.'
    else:
        c += ': <strong>No mods for this show.</strong>'

        watch = [t.mod for t in turfs.where(Turf.state == TURF_LOOKUP['watch'])]
        if watch:
            c += ' ' + ', '.join(at_mention(m) for m in watch)
            c += ' say they could help.'

    c += ' (<a href="https://ptv.dougal.me/turfs/#show-{}">turfs entry</a>)' \
        .format(show.id)
    return c


def comment_on(report, browser):
    c = build_comment(report.report_id, report.show)
    url = '{}/modcp/reports/{}/'.format(BASE, report.report_id)
    open_with_login(browser, url)
    f = browser.get_form(method='post', class_='ipsForm')
    f['report_comment_{}_noscript'.format(report.report_id)] = c
    browser.submit_form(f)
    report.commented = True
    report.save()


# get local IPs: http://stackoverflow.com/a/1267524/344821
_allowed_ips = {'127.0.0.1'}
for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
    _allowed_ips.add(ip)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 53))
_allowed_ips.add(s.getsockname()[0])
s.close()


@app.route('/reports-update/')
def run_update():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip not in _allowed_ips:
        msg = "Can't run this from {}".format(ip)
        return Response(msg, mimetype='text/plain', status=403)

    try:
        if hasattr(g, 'browser'):
            br = g.browser
        else:
            br = g.browser = make_browser()

        for name, report_id in get_reports(br):
            try:
                report = Report.get(Report.report_id == report_id)
            except Report.DoesNotExist:
                show = report_forum(report_id, br)
                report = Report(
                    report_id=report_id, name=name, show=show, commented=False)
                report.save()

            if not report.commented:
                comment_on(report, br)
    except Exception as e:
        info = traceback.format_exc()
        return Response(info, mimetype='text/plain', status=500)

    return Response("", mimetype='text/plain')


if __name__ == '__main__':
    run_update()