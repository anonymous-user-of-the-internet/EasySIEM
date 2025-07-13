from flask import Blueprint, request, render_template, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timezone
from app import db
from models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    User login
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = request.form.get('remember', False)

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            
            # Create new session
            session_id = current_app.session_manager.create_session(
                user.id,
                request.headers.get('User-Agent'),
                request.remote_addr
            )
            session['session_id'] = session_id
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """
    User logout
    """
    # Delete the current session
    if 'session_id' in session:
        current_app.session_manager.delete_session(session['session_id'])
        session.clear()
    
    logout_user()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    User registration (admin only)
    """
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('Admin access required', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        is_admin = 'is_admin' in request.form
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return render_template('register.html')
        
        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            is_admin=is_admin
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'User {username} created successfully', 'success')
        return redirect(url_for('dashboard.index'))
    
    return render_template('register.html')

@auth_bp.route('/profile/sessions')
@login_required
def active_sessions():
    # Get all active sessions for the current user
    sessions = current_app.session_manager.get_user_sessions(current_user.id)
    return render_template('profile/sessions.html', sessions=sessions)

@auth_bp.route('/profile/sessions/revoke/<session_id>')
@login_required
def revoke_session(session_id):
    # Revoke a specific session
    current_app.session_manager.delete_session(session_id)
    flash('Session has been revoked', 'success')
    return redirect(url_for('auth.active_sessions'))

@auth_bp.route('/profile/sessions/revoke-all')
@login_required
def revoke_all_sessions():
    # Revoke all sessions except the current one
    current_session_id = session.get('session_id')
    sessions = current_app.session_manager.get_user_sessions(current_user.id)
    
    for session_data in sessions:
        if session_data['session_id'] != current_session_id:
            current_app.session_manager.delete_session(session_data['session_id'])
    
    flash('All other sessions have been revoked', 'success')
    return redirect(url_for('auth.active_sessions'))
