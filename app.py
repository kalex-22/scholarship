from datetime import datetime, date, timedelta
from functools import wraps
from io import StringIO
import csv
import os
import secrets
from uuid import uuid4
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, abort, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # demo secret changes each restart; configure from environment for deployment
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=15 * 1024 * 1024)
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

# All data below is demonstration data held in memory. It resets when Flask restarts.
users = {
    1: {'id': 1, 'name': 'YouthConnect Admin', 'email': 'admin@youthconnect.local', 'password': generate_password_hash('AdminDemo123!'), 'role': 'admin', 'active': True, 'created': date.today().isoformat()},
    2: {'id': 2, 'name': 'Scholarship Coordinator', 'email': 'coordinator@youthconnect.local', 'password': generate_password_hash('Coordinator123!'), 'role': 'coordinator', 'active': True, 'created': date.today().isoformat()},
}
next_user_id = 3
scholarships = [
    {'id': 1, 'name': 'Barangay Educational Assistance', 'description': 'Demonstration assistance program for eligible local students.', 'level': 'College', 'eligibility': 'Resident student; currently enrolled; submit required documents.', 'benefit': 'Demo assistance: ₱5,000', 'deadline': (date.today()+timedelta(days=30)).isoformat(), 'status': 'Open'},
    {'id': 2, 'name': 'CHED Merit Scholarship', 'description': 'Sample merit-based scholarship listing for interface testing.', 'level': 'College', 'eligibility': 'Meet academic and program requirements.', 'benefit': 'Varies by program', 'deadline': (date.today()+timedelta(days=45)).isoformat(), 'status': 'Open'},
    {'id': 3, 'name': 'Student Financial Assistance', 'description': 'Sample educational support program.', 'level': 'Senior High School', 'eligibility': 'Currently enrolled and able to provide proof of enrollment.', 'benefit': 'Demo educational support', 'deadline': (date.today()+timedelta(days=20)).isoformat(), 'status': 'Open'},
    {'id': 4, 'name': 'Youth Academic Support Program', 'description': 'Sample program supporting student learning needs.', 'level': 'Any', 'eligibility': 'Barangay youth currently studying.', 'benefit': 'Learning materials', 'deadline': (date.today()+timedelta(days=60)).isoformat(), 'status': 'Open'},
]
applications = []
events = [
    {'id': 1, 'title': 'Youth Leadership Seminar', 'date': (date.today()+timedelta(days=1)).isoformat(), 'start': '09:00', 'end': '12:00', 'venue': 'Barangay Hall', 'description': 'A demonstration seminar about youth leadership and community participation.', 'organizer': 'Sangguniang Kabataan', 'deadline': (date.today()+timedelta(days=1)).isoformat(), 'capacity': 80, 'status': 'Published'},
    {'id': 2, 'title': 'Community Clean-Up Drive', 'date': (date.today()+timedelta(days=7)).isoformat(), 'start': '07:00', 'end': '10:00', 'venue': 'Barangay Plaza', 'description': 'Join a community clean-up activity.', 'organizer': 'Youth Volunteers', 'deadline': (date.today()+timedelta(days=6)).isoformat(), 'capacity': 60, 'status': 'Published'},
    {'id': 3, 'title': 'Digital Skills Workshop', 'date': (date.today()+timedelta(days=14)).isoformat(), 'start': '13:00', 'end': '16:00', 'venue': 'Community Learning Center', 'description': 'A sample workshop on digital skills.', 'organizer': 'Youth Development Office', 'deadline': (date.today()+timedelta(days=12)).isoformat(), 'capacity': 40, 'status': 'Published'},
]
announcements = [
    {'id': 1, 'title': 'Youth Leadership Seminar Tomorrow', 'description': 'Registration is open for the youth leadership seminar. Please arrive 15 minutes before the event.', 'category': 'Community Event', 'published': date.today().isoformat(), 'event_date': (date.today()+timedelta(days=1)).isoformat(), 'priority': 'High', 'status': 'Published', 'organizer': 'Sangguniang Kabataan'},
    {'id': 2, 'title': 'Scholarship Applications Are Open', 'description': 'Review the eligibility requirements and submit complete information before the deadline.', 'category': 'Scholarship', 'published': date.today().isoformat(), 'event_date': '', 'priority': 'Normal', 'status': 'Published', 'organizer': 'Scholarship Coordinator'},
]
registrations = []
notifications = []
activity_logs = []
next_application_id = 1
next_event_id = 4
next_announcement_id = 3
next_notification_id = 1


def current_user():
    uid = session.get('user_id')
    return users.get(uid) if uid else None

def log_activity(action, detail=''):
    u = current_user()
    activity_logs.insert(0, {'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'user': u['name'] if u else 'System', 'action': action, 'detail': detail})
    del activity_logs[200:]

def notify(user_id, title, message, kind='notice', link='notifications'):
    global next_notification_id
    notifications.insert(0, {'id': next_notification_id, 'user_id': user_id, 'title': title, 'message': message, 'type': kind, 'created': datetime.now().strftime('%Y-%m-%d %H:%M'), 'read': False, 'link': link})
    next_notification_id += 1

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            u = current_user()
            if not u:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login'))
            if u['role'] not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def event_registrations(event_id):
    return [r for r in registrations if r['event_id'] == event_id]

def user_application(user_id, scholarship_id):
    return next((a for a in applications if a['user_id'] == user_id and a['scholarship_id'] == scholarship_id), None)

def refresh_reminders(user):
    """Generate in-app reminders when a page loads; not a background notification service."""
    if not user: return
    today = date.today()
    for ev in events:
        if ev['status'] != 'Published': continue
        try: event_date = date.fromisoformat(ev['date'])
        except ValueError: continue
        if event_date == today + timedelta(days=1) and any(r['user_id'] == user['id'] and r['event_id'] == ev['id'] for r in registrations):
            key = f"event-tomorrow-{user['id']}-{ev['id']}-{ev['date']}"
            if not any(n.get('key') == key for n in notifications):
                notify(user['id'], f"Reminder: {ev['title']} is tomorrow", f"Scheduled for {ev['start']} at {ev['venue']}.", 'event', 'events')
                notifications[0]['key'] = key
        for sch in scholarships:
            if sch['status'] == 'Open' and sch['deadline'] == (today+timedelta(days=3)).isoformat() and user_application(user['id'], sch['id']):
                key = f"deadline-{user['id']}-{sch['id']}-{sch['deadline']}"
                if not any(n.get('key') == key for n in notifications):
                    notify(user['id'], f"Deadline approaching: {sch['name']}", f"The application deadline is {sch['deadline']}.", 'scholarship', 'applications')
                    notifications[0]['key'] = key

@app.context_processor
def inject_globals():
    u = current_user()
    return {'current_user': u, 'unread_count': sum(1 for n in notifications if u and n['user_id'] == u['id'] and not n['read']), 'today_iso': date.today().isoformat()}

@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user() else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        password = request.form.get('password','')
        user = next((u for u in users.values() if u['email'].lower() == email), None)
        if user and user['active'] and check_password_hash(user['password'], password):
            session.clear(); session['user_id'] = user['id']
            log_activity('Logged in')
            flash(f"Welcome, {user['name']}!", 'success')
            return redirect(url_for('admin_dashboard') if user['role'] in ('admin','coordinator') else url_for('dashboard'))
        flash('Invalid email/password or inactive account.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    global next_user_id
    if request.method == 'POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower()
        password=request.form.get('password',''); confirm=request.form.get('confirm_password','')
        if not name or not email or not password: flash('Complete all required fields.', 'danger')
        elif len(password) < 8: flash('Password must contain at least 8 characters.', 'danger')
        elif password != confirm: flash('Passwords do not match.', 'danger')
        elif any(u['email'].lower()==email for u in users.values()): flash('That email is already registered.', 'danger')
        else:
            users[next_user_id]={'id':next_user_id,'name':name,'email':email,'password':generate_password_hash(password),'role':'student','active':True,'created':date.today().isoformat()}
            session['user_id']=next_user_id; next_user_id+=1
            log_activity('Registered account'); flash('Your demonstration account has been created.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    if current_user(): log_activity('Logged out')
    session.clear(); flash('You have been logged out.', 'success'); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    u=current_user(); refresh_reminders(u)
    if u['role'] in ('admin','coordinator'): return redirect(url_for('admin_dashboard'))
    my_apps=[a for a in applications if a['user_id']==u['id']]
    my_regs=[r for r in registrations if r['user_id']==u['id']]
    latest=[a for a in announcements if a['status']=='Published']
    activity=[x for x in activity_logs if x['user']==u['name']][:5]
    return render_template('user_dashboard.html', scholarships=scholarships, events=[e for e in events if e['status']=='Published'], announcements=latest, my_apps=my_apps, my_regs=my_regs, activity=activity)

@app.route('/scholarships')
@login_required
def scholarship_list():
    q=request.args.get('q','').lower(); level=request.args.get('level','')
    items=[s for s in scholarships if (q in s['name'].lower() or q in s['description'].lower()) and (not level or s['level']==level)]
    return render_template('scholarships.html', scholarships=items, levels=sorted(set(s['level'] for s in scholarships)))

@app.route('/scholarships/<int:scholarship_id>')
@login_required
def scholarship_details(scholarship_id):
    sch=next((s for s in scholarships if s['id']==scholarship_id),None)
    if not sch: abort(404)
    existing=user_application(current_user()['id'],sch['id'])
    return render_template('scholarship_details.html', scholarship=sch, existing=existing)

@app.route('/apply/<int:scholarship_id>', methods=['POST'])
@login_required
def apply_scholarship(scholarship_id):
    global next_application_id
    u=current_user(); sch=next((s for s in scholarships if s['id']==scholarship_id),None)
    if not sch: abort(404)
    if sch['status']!='Open' or sch['deadline'] < date.today().isoformat(): flash('This scholarship is not accepting applications.', 'warning')
    elif user_application(u['id'],sch['id']): flash('You already applied to this scholarship.', 'warning')
    else:
        required=['school','level','phone','reason']
        uploads = [(label, request.files.get(field)) for field, label in [('proof_of_enrollment', 'Proof of enrollment'), ('valid_id', 'Valid ID'), ('grade_record', 'Grade record')]]
        if any(not request.form.get(k,'').strip() for k in required): flash('Complete all required application fields.', 'danger')
        elif any(not file or not file.filename for _, file in uploads): flash('Upload all required scholarship documents.', 'danger')
        elif any('.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ALLOWED_IMAGE_EXTENSIONS for _, file in uploads): flash('Documents must be JPG, PNG, or WEBP images.', 'danger')
        elif any(file.mimetype not in ('image/jpeg', 'image/png', 'image/webp') for _, file in uploads): flash('Upload valid JPG, PNG, or WEBP images.', 'danger')
        elif not request.form.get('declaration'): flash('Please confirm the declaration.', 'danger')
        else:
            saved_documents = []
            for label, file in uploads:
                extension = file.filename.rsplit('.', 1)[1].lower()
                stored_name = f'{uuid4().hex}.{extension}'
                file.save(os.path.join(UPLOAD_FOLDER, stored_name))
                saved_documents.append({'label': label, 'filename': stored_name, 'viewed': False})
            app_record={'id':next_application_id,'reference':f'YC-{date.today():%y%m%d}-{next_application_id:04d}','user_id':u['id'],'user_name':u['name'],'scholarship_id':sch['id'],'scholarship_name':sch['name'],'school':request.form['school'].strip(),'level':request.form['level'],'phone':request.form['phone'].strip(),'reason':request.form['reason'].strip(),'documents':saved_documents,'status':'Pending','note':'','submitted':datetime.now().strftime('%Y-%m-%d %H:%M')}
            applications.append(app_record); next_application_id+=1
            notify(u['id'],'Application submitted',f"Your application for {sch['name']} was submitted.",'application','applications')
            log_activity('Submitted scholarship application', sch['name']); flash('Application submitted successfully.', 'success')
    return redirect(url_for('applications_page'))

@app.route('/applications')
@login_required
def applications_page():
    u=current_user(); items=applications if u['role'] in ('admin','coordinator') else [a for a in applications if a['user_id']==u['id']]
    return render_template('applications.html', applications=items)

@app.route('/admin/applications/<int:application_id>/documents/<int:document_index>')
@roles_required('admin','coordinator')
def view_application_document(application_id, document_index):
    a=next((x for x in applications if x['id']==application_id),None)
    if not a: abort(404)
    docs=a.get('documents', [])
    if document_index < 0 or document_index >= len(docs): abort(404)
    doc=docs[document_index]
    doc['viewed']=True
    return send_from_directory(UPLOAD_FOLDER, doc['filename'], mimetype='image/' + doc['filename'].rsplit('.', 1)[1], as_attachment=False)

@app.route('/admin/applications/<int:application_id>/status', methods=['POST'])
@roles_required('admin','coordinator')
def update_application(application_id):
    a=next((x for x in applications if x['id']==application_id),None)
    if not a: abort(404)
    status=request.form.get('status','Pending')
    if status not in ('Pending','Under Review','Incomplete','Approved','Rejected'): abort(400)
    if status == 'Approved' and (not a.get('documents') or not all(doc.get('viewed') for doc in a['documents'])):
        flash('Open and review every uploaded document before approving this application.', 'warning')
        return redirect(request.referrer or url_for('applications_page'))
    a['status']=status; a['note']=request.form.get('note','').strip()
    notify(a['user_id'],'Application status updated',f"{a['scholarship_name']}: {status}. {a['note']}",'application','applications')
    log_activity('Updated application status',f"{a['reference']} → {status}"); flash('Application status updated.', 'success')
    return redirect(request.referrer or url_for('applications_page'))

@app.route('/events')
@login_required
def event_list():
    q=request.args.get('q','').lower()
    items=[e for e in events if e['status']=='Published' and (q in e['title'].lower() or q in e['venue'].lower())]
    my_ids={r['event_id'] for r in registrations if r['user_id']==current_user()['id']}
    return render_template('events.html', events=items, my_event_ids=my_ids, registrations=registrations)

@app.route('/events/<int:event_id>')
@login_required
def event_details(event_id):
    ev=next((e for e in events if e['id']==event_id),None)
    if not ev: abort(404)
    registered=any(r['event_id']==event_id and r['user_id']==current_user()['id'] for r in registrations)
    return render_template('event_details.html', event=ev, registered=registered, count=len(event_registrations(event_id)))

@app.route('/events/<int:event_id>/register', methods=['POST'])
@login_required
def register_event(event_id):
    ev=next((e for e in events if e['id']==event_id),None)
    if not ev: abort(404)
    u=current_user()
    if ev['status']!='Published' or ev['date']<date.today().isoformat() or ev['deadline']<date.today().isoformat(): flash('Registration is closed for this event.', 'warning')
    elif any(r['event_id']==event_id and r['user_id']==u['id'] for r in registrations): flash('You are already registered.', 'warning')
    elif len(event_registrations(event_id))>=int(ev['capacity']): flash('This event has reached capacity.', 'danger')
    else:
        registrations.append({'id':len(registrations)+1,'event_id':event_id,'event_title':ev['title'],'user_id':u['id'],'user_name':u['name'],'registered':datetime.now().strftime('%Y-%m-%d %H:%M'),'attendance':'Not recorded'})
        notify(u['id'],'Event registration confirmed',f"You registered for {ev['title']} on {ev['date']}.",'event','events')
        log_activity('Registered for event',ev['title']); flash('Event registration confirmed.', 'success')
    return redirect(url_for('event_list'))

@app.route('/events/<int:event_id>/cancel-registration', methods=['POST'])
@login_required
def cancel_registration(event_id):
    u=current_user(); r=next((x for x in registrations if x['event_id']==event_id and x['user_id']==u['id']),None)
    if r: registrations.remove(r); log_activity('Cancelled event registration',r['event_title']); flash('Registration cancelled.', 'success')
    return redirect(url_for('event_list'))

@app.route('/announcements')
@login_required
def announcement_list():
    q=request.args.get('q','').lower(); cat=request.args.get('category','')
    items=[a for a in announcements if a['status']=='Published' and (q in a['title'].lower() or q in a['description'].lower()) and (not cat or a['category']==cat)]
    return render_template('announcements.html', announcements=items, categories=sorted(set(a['category'] for a in announcements)))

@app.route('/notifications', methods=['GET','POST'])
@login_required
def notification_page():
    u=current_user(); refresh_reminders(u)
    items=[n for n in notifications if n['user_id']==u['id']]
    if request.method=='POST':
        action=request.form.get('action'); nid=request.form.get('id')
        if action=='read_all':
            for n in items: n['read']=True
        elif action=='read' and nid:
            for n in items:
                if str(n['id'])==nid: n['read']=True
        elif action=='dismiss' and nid:
            notifications[:]=[n for n in notifications if not (n['user_id']==u['id'] and str(n['id'])==nid)]
        return redirect(url_for('notification_page'))
    return render_template('notifications.html', notifications=items)

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    u=current_user()
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower()
        if not name or not email: flash('Name and email are required.', 'danger')
        elif any(x['id']!=u['id'] and x['email'].lower()==email for x in users.values()): flash('Email is already in use.', 'danger')
        else: u['name']=name; u['email']=email; log_activity('Updated profile'); flash('Profile updated.', 'success'); return redirect(url_for('profile'))
    return render_template('profile.html')

@app.route('/settings')
@login_required
def settings(): return render_template('settings.html')

@app.route('/admin')
@roles_required('admin','coordinator')
def admin_dashboard():
    total=len(applications); approved=sum(a['status']=='Approved' for a in applications)
    chart_status={s:sum(a['status']==s for a in applications) for s in ('Approved','Pending','Under Review','Rejected','Incomplete')}
    participation=[{'title':e['title'],'registrations':len(event_registrations(e['id'])),'attendance':sum(r['attendance']=='Present' for r in event_registrations(e['id']))} for e in events]
    program_stats=[]
    for s in scholarships:
        apps=[a for a in applications if a['scholarship_id']==s['id']]; count=len(apps); ok=sum(a['status']=='Approved' for a in apps)
        program_stats.append({'name':s['name'],'total':count,'approved':ok,'pending':sum(a['status']=='Pending' for a in apps),'rate':round(ok/count*100,1) if count else 0})
    return render_template('admin_dashboard.html', applications=applications, events=events, announcements=announcements, chart_status=chart_status, participation=participation, program_stats=program_stats, registrations=registrations, users=list(users.values()))

@app.route('/admin/scholarships', methods=['GET','POST'])
@roles_required('admin','coordinator')
def admin_scholarships():
    if request.method=='POST':
        name=request.form.get('name','').strip(); deadline=request.form.get('deadline','')
        if not name or not deadline: flash('Scholarship name and deadline are required.', 'danger')
        else:
            scholarships.append({'id':max([s['id'] for s in scholarships],default=0)+1,'name':name,'description':request.form.get('description','').strip(),'level':request.form.get('level','Any'),'eligibility':request.form.get('eligibility','').strip(),'benefit':request.form.get('benefit','').strip(),'deadline':deadline,'status':request.form.get('status','Open')})
            log_activity('Created scholarship',name); flash('Scholarship created.', 'success')
        return redirect(url_for('admin_scholarships'))
    return render_template('admin_scholarships.html', scholarships=scholarships)

@app.route('/admin/events', methods=['GET','POST'])
@roles_required('admin','coordinator')
def admin_events():
    global next_event_id
    if request.method=='POST':
        title=request.form.get('title','').strip(); event_date=request.form.get('date',''); deadline=request.form.get('deadline','')
        if not title or not event_date or not deadline: flash('Title, date, and registration deadline are required.', 'danger')
        else:
            ev={'id':next_event_id,'title':title,'date':event_date,'start':request.form.get('start','09:00'),'end':request.form.get('end','10:00'),'venue':request.form.get('venue','').strip(),'description':request.form.get('description','').strip(),'organizer':request.form.get('organizer','Barangay Youth'),'deadline':deadline,'capacity':max(1,int(request.form.get('capacity',50))),'status':request.form.get('status','Published')}
            events.append(ev); next_event_id+=1
            if ev['status']=='Published':
                for u in users.values():
                    if u['role']=='student': notify(u['id'],'New youth event',f"{title} on {event_date} at {ev['venue']}.",'event','events')
            log_activity('Created event',title); flash('Event created.', 'success')
        return redirect(url_for('admin_events'))
    return render_template('admin_events.html', events=events, registrations=registrations)

@app.route('/admin/events/<int:event_id>/status', methods=['POST'])
@roles_required('admin','coordinator')
def event_status(event_id):
    ev=next((e for e in events if e['id']==event_id),None)
    if not ev: abort(404)
    status=request.form.get('status','Published')
    if status not in ('Published','Draft','Cancelled'): abort(400)
    ev['status']=status
    if status=='Cancelled':
        for r in event_registrations(event_id): notify(r['user_id'],'Event cancelled',f"{ev['title']} has been cancelled.",'event','events')
    log_activity('Changed event status',f"{ev['title']}: {status}"); flash('Event status updated.', 'success')
    return redirect(url_for('admin_events'))

@app.route('/admin/announcements', methods=['GET','POST'])
@roles_required('admin','coordinator')
def admin_announcements():
    global next_announcement_id
    if request.method=='POST':
        title=request.form.get('title','').strip(); description=request.form.get('description','').strip()
        if not title or not description: flash('Title and description are required.', 'danger')
        else:
            a={'id':next_announcement_id,'title':title,'description':description,'category':request.form.get('category','Important Notice'),'published':request.form.get('published') or date.today().isoformat(),'event_date':request.form.get('event_date',''),'priority':request.form.get('priority','Normal'),'status':request.form.get('status','Published'),'organizer':current_user()['name']}
            announcements.insert(0,a); next_announcement_id+=1
            if a['status']=='Published':
                for u in users.values():
                    if u['role']=='student': notify(u['id'],'New announcement',title,'announcement','announcements')
            log_activity('Created announcement',title); flash('Announcement saved.', 'success')
        return redirect(url_for('admin_announcements'))
    return render_template('admin_announcements.html', announcements=announcements)

@app.route('/admin/registrations')
@roles_required('admin','coordinator')
def admin_registrations(): return render_template('registrations.html', registrations=registrations, events=events)

@app.route('/admin/registrations/<int:registration_id>/attendance', methods=['POST'])
@roles_required('admin','coordinator')
def attendance(registration_id):
    r=next((x for x in registrations if x['id']==registration_id),None)
    if not r: abort(404)
    value=request.form.get('attendance','Not recorded')
    if value not in ('Present','Absent','Not recorded'): abort(400)
    r['attendance']=value; log_activity('Recorded attendance',f"{r['user_name']}: {value}"); flash('Attendance updated.', 'success')
    return redirect(url_for('admin_registrations'))

@app.route('/admin/analytics')
@roles_required('admin','coordinator')
def analytics():
    status_counts={s:sum(a['status']==s for a in applications) for s in ('Approved','Pending','Under Review','Rejected','Incomplete')}
    event_stats=[{'title':e['title'],'registrations':len(event_registrations(e['id'])),'attendees':sum(r['attendance']=='Present' for r in event_registrations(e['id'])),'rate':round(sum(r['attendance']=='Present' for r in event_registrations(e['id']))/len(event_registrations(e['id']))*100,1) if event_registrations(e['id']) else 0} for e in events]
    top_event=max(event_stats,key=lambda x:x['registrations'],default=None)
    top_sch=max(scholarships,key=lambda s:sum(a['scholarship_id']==s['id'] for a in applications),default=None)
    insights=[]
    if top_event and top_event['registrations']: insights.append(f"{top_event['title']} has the most registrations ({top_event['registrations']}).")
    if top_sch: insights.append(f"{top_sch['name']} has {sum(a['scholarship_id']==top_sch['id'] for a in applications)} application(s).")
    insights.append(f"{status_counts['Pending']} application(s) are pending review.")
    incomplete=sum(a['status']=='Incomplete' for a in applications); insights.append(f"{incomplete} application(s) are marked incomplete.")
    return render_template('analytics.html', status_counts=status_counts, event_stats=event_stats, insights=insights, applications=applications, scholarships=scholarships, announcements=announcements, registrations=registrations)

@app.route('/admin/reports')
@roles_required('admin','coordinator')
def reports(): return render_template('reports.html')

@app.route('/admin/reports/<kind>.csv')
@roles_required('admin','coordinator')
def export_csv(kind):
    data_map={
      'applications': (['Reference','Student','Scholarship','School','Status','Submitted'], [[a['reference'],a['user_name'],a['scholarship_name'],a['school'],a['status'],a['submitted']] for a in applications]),
      'scholarships': (['Program','Total applications','Approved','Pending','Approval rate'], [[s['name'],sum(a['scholarship_id']==s['id'] for a in applications),sum(a['scholarship_id']==s['id'] and a['status']=='Approved' for a in applications),sum(a['scholarship_id']==s['id'] and a['status']=='Pending' for a in applications),round(sum(a['scholarship_id']==s['id'] and a['status']=='Approved' for a in applications)/max(1,sum(a['scholarship_id']==s['id'] for a in applications))*100,1)] for s in scholarships]),
      'registrations': (['Event','Participant','Registered','Attendance'], [[r['event_title'],r['user_name'],r['registered'],r['attendance']] for r in registrations]),
      'attendance': (['Event','Participant','Attendance'], [[r['event_title'],r['user_name'],r['attendance']] for r in registrations]),
      'announcements': (['Title','Category','Published','Priority','Status'], [[a['title'],a['category'],a['published'],a['priority'],a['status']] for a in announcements]),
      'notifications': (['User ID','Title','Message','Type','Created','Read'], [[n['user_id'],n['title'],n['message'],n['type'],n['created'],n['read']] for n in notifications]),
    }
    if kind not in data_map: abort(404)
    output=StringIO(); writer=csv.writer(output); writer.writerow(data_map[kind][0]); writer.writerows(data_map[kind][1])
    response=make_response('\ufeff'+output.getvalue()); response.headers['Content-Type']='text/csv; charset=utf-8'; response.headers['Content-Disposition']=f'attachment; filename=youthconnect_{kind}.csv'
    log_activity('Exported report',kind); return response

@app.route('/admin/users', methods=['GET','POST'])
@roles_required('admin')
def user_management():
    global next_user_id
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); role=request.form.get('role','student')
        if role not in ('student','coordinator','admin'): abort(400)
        if not name or not email or len(password)<8: flash('Enter name, email, and a password of at least 8 characters.', 'danger')
        elif any(u['email'].lower()==email for u in users.values()): flash('Email already exists.', 'danger')
        else:
            users[next_user_id]={'id':next_user_id,'name':name,'email':email,'password':generate_password_hash(password),'role':role,'active':True,'created':date.today().isoformat()}; next_user_id+=1
            log_activity('Created user',email); flash('User created.', 'success')
        return redirect(url_for('user_management'))
    return render_template('users.html', users=list(users.values()))

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@roles_required('admin')
def toggle_user(user_id):
    u=users.get(user_id)
    if not u: abort(404)
    if u['id']==current_user()['id']: flash('You cannot deactivate your own account.', 'warning')
    else: u['active']=not u['active']; log_activity('Changed user active status',u['email']); flash('User account status updated.', 'success')
    return redirect(url_for('user_management'))

@app.route('/admin/activity')
@roles_required('admin')
def activity_page(): return render_template('activity_logs.html', activity_logs=activity_logs)

@app.route('/api/summary')
@roles_required('admin','coordinator')
def api_summary():
    return jsonify({'applications':len(applications),'pending':sum(a['status']=='Pending' for a in applications),'events':sum(e['status']=='Published' and e['date']>=date.today().isoformat() for e in events),'registrations':len(registrations),'announcements':sum(a['status']=='Published' for a in announcements)})

@app.errorhandler(403)
def forbidden(error): return render_template('error.html', code=403, message='You do not have permission to access this page.'),403
@app.errorhandler(404)
def not_found(error): return render_template('error.html', code=404, message='The requested page or record could not be found.'),404

if __name__ == '__main__':
    app.run(debug=True)
