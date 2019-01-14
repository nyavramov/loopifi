from datetime import datetime, timedelta
from dateutil import rrule
from flask import Flask, request, redirect, render_template, url_for, \
    send_file, flash
from flask_migrate import Migrate
from flask_rq2 import RQ
from flask_sqlalchemy import SQLAlchemy
from sentry_sdk.integrations.flask import FlaskIntegration

from downloader import download_video
from loops import makeLoops
from parrots import random_parrot

import logging
import re
import sentry_sdk
import shutil
import os

###############################################################################

logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO'))
logger = logging.getLogger(__name__)

sentry_sdk.init(
    dsn="https://c9a949f71fee489795e1c655e08e2d7c@sentry.io/1314208",
    integrations=[FlaskIntegration()]
)

app = Flask(__name__)

logger.debug('Flask app initialized')

# Development Settings Initialized First
app.secret_key = "FSD13ZrsdfsdfbR~XASASjmNADSDX/,?RTk"

# Set maximum upload size to 16 MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

app.config['RQ_REDIS_URL'] = 'redis://localhost:6379/0'

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'res')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# see http://www.daniloaz.com/en/how-to-create-a-user-in-mysql-mariadb-and-grant-permissions-on-a-specific-database/
# for creating the user with correct username/password
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://looper:nevergonnagiveyouup@localhost/loops'

logger.debug('Database URI: %s', app.config['SQLALCHEMY_DATABASE_URI'])

# Override With Production Settings in Docker
app.config.from_envvar('LOOPER_SETTINGS', silent=True)

logger.debug('Flask app configured')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    logger.debug('Upload folder not found, creating..')
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Override the SQLAlchemy class to use the `pool_pre_ping` feature,
# which should eliminate the `MySQL server has gone away...` errors
# https://stackoverflow.com/a/45078959
# https://github.com/mitsuhiko/flask-sqlalchemy/issues/589#issuecomment-361075700
class MySQLAlchemy(SQLAlchemy):
    def apply_pool_defaults(self, app, options):
        SQLAlchemy.apply_pool_defaults(self, app, options)
        options['pool_pre_ping'] = True

db = MySQLAlchemy(app)
migrate = Migrate(app, db)
rq = RQ(app)

logger.debug('Flask extensions loaded')


###############################################################################


class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    webm_location = db.Column(db.String(128))
    gif_location = db.Column(db.String(128))
    mp4_location = db.Column(db.String(128))
    score = db.Column(db.Float, default=0)
    start_frame = db.Column(db.Integer, default=0)
    end_frame = db.Column(db.Integer, default=0)

    record_id = db.Column(db.Integer, db.ForeignKey(
        'record.id'), nullable=False)


class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    done = db.Column(db.Boolean, default=False)
    failed = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(32), default='In Queue')
    progress = db.Column(db.Integer, default=0)
    job_id = db.Column(db.String(64), default='-')
    created_at = db.Column(db.DateTime, nullable=False,
                           default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    start_seconds = db.Column(db.Integer, default=0)
    end_seconds = db.Column(db.Integer, default=30)
    url = db.Column(db.String(128), default=None)
    
    videos = db.relationship('Video')

###############################################################################


@rq.job
def loopify(_id, path, url=None, sound=True, stabilize=True):
    # define our callback for updating the job progress
    def update_record(status=None, progress=None):
        if status is not None:
            record.status = status

        if progress is not None:
            record.progress = progress

        db.session.commit()

    record = Record.query.get(_id)

    # do the work
    try:
        # download the video, if necessary
        if url is not None:
            record.status = 'Downloading video...'
            db.session.commit()

            # download the youtube video
            download_video(url,
                           path,
                           record.start_seconds,
                           record.end_seconds)

            # correct the seconds offsets for a ~30 second video
            # because the downloaded video already starts at record.start_seconds
            record.end_seconds = record.end_seconds - record.start_seconds
            record.start_seconds = 0

        record.status = 'Loopifying...'
        db.session.commit()

        result = makeLoops(
            path,
            callback=update_record,
            startTime=record.start_seconds,
            endTime=record.end_seconds,
            soundEnabled=sound,
            stabilizeEnabled=stabilize
        )

        for r in result:
            video = Video(webm_location=os.path.basename(r.webmLocation),
                          gif_location=os.path.basename(r.gifLocation),
                          mp4_location=os.path.basename(r.mp4Location),
                          score=r.score,
                          start_frame=r.startFrameNumber,
                          end_frame=r.endFrameNumber,
                          record_id=record.id)
            db.session.add(video)
    except Exception as e:
        sentry_sdk.capture_exception()
        logger.exception('Job loopify failed')
        record.failed = True
    finally:
        record.done = True
        record.finished_at = datetime.utcnow()
        db.session.commit()


###############################################################################


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/about', methods=['GET'])
def about():
    return render_template('about.html')


@app.route('/browse', methods=['GET'])
def browse():
    pagination = Record.query \
        .filter_by(done=True) \
        .filter_by(failed=False) \
        .order_by(Record.id.desc()) \
        .paginate(per_page=10, error_out=False)

    return render_template('browse.html', pagination=pagination)


@app.route('/create', methods=['POST'])
def create():
    # validate request
    uploaded_file = None
    url = None

    # check for create by URL or by file upload

    # check if the post request has the file part
    if 'file' in request.files:
        target = request.files['file']

        # if user does not select file, browser also
        # submit an empty part without filename
        if target.filename == '':
            flash('No file selected!')
            return redirect(url_for('index'))

        if not target.filename.endswith('.mp4'):
            flash('Invalid file format!')
            return redirect(url_for('index'))

        uploaded_file = request.files['file']
    else:
        # grab URL, if possible
        url = request.form.get('url', None)

    # fail on missing file _and_ url
    if uploaded_file is None and url is None:
        flash('Missing URL or file!')
        return redirect(url_for('index'))

    # check timestamps
    startTimestamp = request.form.get('startTimestamp', None)
    endTimestamp = request.form.get('endTimestamp', None)

    if request.form.get('enableSound'):
        sound = True
    else: 
        sound = False

    if request.form.get('stabilizeVideo'):
        stabilize = True
    else:
        stabilize = False

    if startTimestamp is None or endTimestamp is None:
        flash('Missing timestamp(s)!')
        return redirect(url_for('index'))

    valid_re = re.compile(r'\d?\d:\d\d')

    if not valid_re.match(startTimestamp) or not valid_re.match(endTimestamp):
        flash('Incorrectly formatted timestamp(s)!')
        return redirect(url_for('index'))

    startMinutes, startSeconds = startTimestamp.split(':')
    endMinutes, endSeconds = endTimestamp.split(':')

    startTotalSeconds = (int(startMinutes) * 60) + int(startSeconds)
    endTotalSeconds = (int(endMinutes) * 60) + int(endSeconds)

    if startTotalSeconds >= endTotalSeconds:
        flash('Negative time difference between timestamps!')
        return redirect(url_for('index'))

    if (endTotalSeconds - startTotalSeconds) > 30:
        flash('Max 30s difference between timestamps!')
        return redirect(url_for('index'))

    # valid request, proceed to create job

    record = Record(start_seconds=startTotalSeconds,
                    end_seconds=endTotalSeconds,
                    url=url)

    db.session.add(record)
    db.session.commit()

    folder = os.path.join(app.config['UPLOAD_FOLDER'], '{}'.format(record.id))

    if os.path.exists(folder):
        shutil.rmtree(folder)

    os.makedirs(folder)

    filename = 'video.mp4'
    path = os.path.join(folder, filename)

    if uploaded_file is not None:
        uploaded_file.save(path)

    # enqueue with flask rq
    job = loopify.queue(record.id, path, url, sound, stabilize)

    record.job_id = job.id
    db.session.commit()

    # redirect to loading page
    return redirect(url_for('access', _id=record.id))


@app.route('/loops/<_id>', methods=['GET'])
def access(_id):
    record = Record.query.get_or_404(_id)

    if not record.done:
        # get position in queue
        queue = rq.get_queue()

        try:
            position = queue.job_ids.index(record.job_id) + 1
        except ValueError:
            position = None

        return render_template('waiting.html',
                               job=record,
                               position=position,
                               parrot=random_parrot())

    if record.failed:
        return render_template('failed.html')

    maxScore = max(video.score for video in record.videos)

    return render_template('results.html', record=record, maxScore=maxScore)

@app.route('/stats')
def stats():
    # generate data for the charts

    # first item in array is 6 days ago, then 5, 4, 3, 2, 1 and today
    uploadsPerDay = []
    averageTimeToProcessPerDay = []
    totalUploads = []

    # prepare the relevant dates
    now = datetime.now()
    weekAgo = now - timedelta(days=6)

    # reset `weekAgo` to 12:00AM
    weekAgo = datetime(weekAgo.year,
                       weekAgo.month,
                       weekAgo.day)

    # count of all records created before 6 days ago
    totalCount = Record.query \
                       .filter_by(done=True) \
                       .filter_by(failed=False) \
                       .filter(Record.created_at < weekAgo) \
                       .count()

    # for each day, starting from 6 days ago and ending today
    for dt in rrule.rrule(rrule.DAILY, dtstart=weekAgo, until=now):
        # we grab the relevant records by checking that `created_at`
        # is between 12:00AM and 11:59PM for this day

        # 12:00AM of this day
        start = datetime(dt.year, dt.month, dt.day)

        # 11:59PM of this day
        end = datetime(dt.year,
                       dt.month,
                       dt.day,
                       hour=23,
                       minute=59,
                       second=59)

        # ignore records that are not done (because they do not have
        # the `finished_at` timestamp for average calculation) and
        # uploads that failed to process
        records = Record.query \
                        .filter(
                            Record.created_at.between(start, end)
                        ) \
            .filter_by(done=True) \
            .filter_by(failed=False) \
            .all()

        # grab count of uploads for this day
        count = len(records)

        # update total count at this point
        totalCount += count

        # calculate average time to process for this day
        total_time = sum(
            (r.finished_at - r.created_at).seconds for r in records
        )

        average = 0

        if count > 0:
            average = round(total_time / count, 2)

        # add data to be displayed
        totalUploads.append(totalCount)
        uploadsPerDay.append(count)
        averageTimeToProcessPerDay.append(average)

    return render_template('stats.html',
                           uploadsPerDay=uploadsPerDay,
                           averageTimeToProcessPerDay=averageTimeToProcessPerDay,
                           totalUploads=totalUploads)


###############################################################################

if __name__ == '__main__':
    app.run('localhost', debug=True)
