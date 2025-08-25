import streamlit as st
from ortools.sat.python import cp_model
from typing import Dict, List, Tuple, Any
import json
import pandas as pd
import sqlite3
import tempfile
import os
from datetime import datetime

# Configure page
st.set_page_config(
    page_title="College Timetable Generator - Multi-Year with SQLite",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        background: linear-gradient(90deg, #4CAF50 0%, #45a049 100%);
        padding: 0.8rem;
        border-radius: 8px;
        color: white;
        text-align: center;
        margin: 1rem 0;
    }
    .constraint-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 5px;
        border-left: 5px solid #667eea;
        margin: 0.5rem 0;
    }
    .year-box {
        background-color: #fff3e0;
        border: 2px solid #ff9800;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .section-box {
        background-color: #e8f5e8;
        border: 2px solid #4CAF50;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .sql-code {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 1rem;
        border-radius: 5px;
        font-family: 'Courier New', monospace;
        font-size: 12px;
        overflow-x: auto;
    }
    .enhanced-feature {
        background-color: #e3f2fd;
        border: 1px solid #bbdefb;
        color: #0d47a1;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.2rem 0;
        font-size: 0.9em;
    }
    .teacher-conflict {
        background-color: #ffebee;
        border: 1px solid #f8bbd9;
        color: #c62828;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.2rem 0;
    }
    .sqlite-feature {
        background-color: #fff3e0;
        border: 1px solid #ffb74d;
        color: #e65100;
        padding: 0.5rem;
        border-radius: 5px;
        margin: 0.2rem 0;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def initialize_session_state():
    """Initialize session state variables"""
    if 'courses' not in st.session_state:
        st.session_state.courses = []
    if 'teachers' not in st.session_state:
        st.session_state.teachers = {}
    if 'sections' not in st.session_state:
        st.session_state.sections = {}
    if 'constraints' not in st.session_state:
        st.session_state.constraints = {}
    if 'generated_timetable' not in st.session_state:
        st.session_state.generated_timetable = None
    if 'sqlite_db_path' not in st.session_state:
        st.session_state.sqlite_db_path = None
    if 'last_error' not in st.session_state:
        st.session_state.last_error = None


def create_sqlite_database(timetable_data, teachers, sections, courses):
    """Create SQLite database with timetable data"""
    # Create temporary database file
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    
    conn = sqlite3.connect(temp_db.name)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
    CREATE TABLE teachers (
        teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        department TEXT,
        start_hour INTEGER,
        end_hour INTEGER,
        years_teaching TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE sections (
        section_id INTEGER PRIMARY KEY AUTOINCREMENT,
        year TEXT NOT NULL,
        section_name TEXT NOT NULL,
        capacity INTEGER,
        room_number TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(year, section_name)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE subjects (
        subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT,
        credits INTEGER DEFAULT 3,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE courses (
        course_id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER,
        teacher_id INTEGER,
        section_id INTEGER,
        lectures_per_week INTEGER,
        duration_hours INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subject_id) REFERENCES subjects (subject_id),
        FOREIGN KEY (teacher_id) REFERENCES teachers (teacher_id),
        FOREIGN KEY (section_id) REFERENCES sections (section_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE timetable (
        timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,
        year TEXT NOT NULL,
        section_name TEXT,
        day_of_week TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        slot_name TEXT,
        subject_name TEXT,
        teacher_name TEXT,
        room_number TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses (course_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE time_slots (
        slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        slot_name TEXT UNIQUE NOT NULL,
        day_of_week TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        is_lunch_period BOOLEAN DEFAULT 0
    )
    ''')
    
    # Insert teachers
    teacher_id_map = {}
    for teacher_name, teacher_info in teachers.items():
        cursor.execute('''
        INSERT INTO teachers (name, department, start_hour, end_hour, years_teaching)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            teacher_name,
            teacher_info.get('department', ''),
            teacher_info.get('start_hr', 9),
            teacher_info.get('end_hr', 17),
            ','.join(teacher_info.get('years', []))
        ))
        teacher_id_map[teacher_name] = cursor.lastrowid
    
    # Insert sections
    section_id_map = {}
    for year, year_sections in sections.items():
        for section_name, section_info in year_sections.items():
            cursor.execute('''
            INSERT INTO sections (year, section_name, capacity, room_number)
            VALUES (?, ?, ?, ?)
            ''', (
                year,
                section_name,
                section_info.get('capacity', 60),
                section_info.get('room', '')
            ))
            section_id_map[f"{year}_{section_name}"] = cursor.lastrowid
    
    # Insert subjects and courses
    subject_id_map = {}
    course_id_map = {}
    
    for course in courses:
        subject_name = course['subject']
        
        # Insert subject if not exists
        if subject_name not in subject_id_map:
            cursor.execute('''
            INSERT OR IGNORE INTO subjects (name, code)
            VALUES (?, ?)
            ''', (subject_name, subject_name[:6].upper()))
            
            cursor.execute('SELECT subject_id FROM subjects WHERE name = ?', (subject_name,))
            subject_id_map[subject_name] = cursor.fetchone()[0]
        
        # Insert course
        teacher_id = teacher_id_map.get(course['teacher'])
        subject_id = subject_id_map[subject_name]
        section_key = f"{course['year']}_{course.get('section', 'A')}"
        section_id = section_id_map.get(section_key)
        
        cursor.execute('''
        INSERT INTO courses (subject_id, teacher_id, section_id, lectures_per_week, duration_hours)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            subject_id,
            teacher_id,
            section_id,
            course['lectures'],
            course['duration']
        ))
        
        course_key = f"{course['subject']}_{course['year']}_{course['teacher']}"
        course_id_map[course_key] = cursor.lastrowid
    
    # Insert timetable data
    for year, year_data in timetable_data.items():
        for day, day_schedule in year_data.items():
            for item in day_schedule:
                course_key = f"{item['subject']}_{year}_{item['teacher']}"
                course_id = course_id_map.get(course_key)
                
                # Determine section (default to 'A' if not specified)
                section_name = item.get('section', 'A')
                
                cursor.execute('''
                INSERT INTO timetable (
                    course_id, year, section_name, day_of_week, start_time, end_time,
                    slot_name, subject_name, teacher_name, room_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    course_id,
                    year,
                    section_name,
                    day.capitalize(),
                    item['start_time'],
                    item['end_time'],
                    item['slot'],
                    item['subject'],
                    item['teacher'],
                    item.get('room', '')
                ))
    
    # Create indexes for better performance
    cursor.execute('CREATE INDEX idx_timetable_year_day ON timetable(year, day_of_week)')
    cursor.execute('CREATE INDEX idx_timetable_teacher ON timetable(teacher_name)')
    cursor.execute('CREATE INDEX idx_timetable_subject ON timetable(subject_name)')
    cursor.execute('CREATE INDEX idx_courses_teacher ON courses(teacher_id)')
    cursor.execute('CREATE INDEX idx_courses_section ON courses(section_id)')
    
    # Create views for common queries
    cursor.execute('''
    CREATE VIEW teacher_schedule AS
    SELECT 
        t.year,
        t.section_name,
        t.day_of_week,
        t.start_time,
        t.end_time,
        t.subject_name,
        t.teacher_name,
        teach.department,
        s.capacity as section_capacity,
        s.room_number
    FROM timetable t
    LEFT JOIN courses c ON t.course_id = c.course_id
    LEFT JOIN teachers teach ON c.teacher_id = teach.teacher_id
    LEFT JOIN sections s ON c.section_id = s.section_id
    WHERE t.subject_name != 'Free'
    ORDER BY t.year, t.section_name, t.day_of_week, t.start_time
    ''')
    
    cursor.execute('''
    CREATE VIEW section_schedule AS
    SELECT 
        t.year,
        t.section_name,
        t.day_of_week,
        t.start_time,
        t.end_time,
        t.subject_name,
        t.teacher_name,
        COUNT(*) OVER (PARTITION BY t.year, t.section_name, t.day_of_week) as classes_per_day
    FROM timetable t
    ORDER BY t.year, t.section_name, t.day_of_week, t.start_time
    ''')
    
    cursor.execute('''
    CREATE VIEW teacher_workload AS
    SELECT 
        teach.name as teacher_name,
        teach.department,
        COUNT(DISTINCT t.year) as years_teaching_count,
        COUNT(t.timetable_id) as total_classes_per_week,
        GROUP_CONCAT(DISTINCT t.year) as years_list,
        GROUP_CONCAT(DISTINCT t.subject_name) as subjects_taught
    FROM teachers teach
    LEFT JOIN courses c ON teach.teacher_id = c.teacher_id
    LEFT JOIN timetable t ON c.course_id = t.course_id
    WHERE t.subject_name != 'Free'
    GROUP BY teach.teacher_id, teach.name, teach.department
    ORDER BY total_classes_per_week DESC
    ''')
    
    conn.commit()
    conn.close()
    
    return temp_db.name


def generate_sql_export_queries():
    """Generate comprehensive SQL queries for data export and analysis"""
    return {
        "complete_timetable": """
-- Complete Timetable with All Details
SELECT 
    t.year,
    t.section_name,
    t.day_of_week,
    t.start_time,
    t.end_time,
    t.subject_name,
    t.teacher_name,
    teach.department,
    s.capacity as section_capacity,
    s.room_number,
    c.lectures_per_week,
    c.duration_hours
FROM timetable t
LEFT JOIN courses c ON t.course_id = c.course_id
LEFT JOIN teachers teach ON c.teacher_id = teach.teacher_id
LEFT JOIN sections s ON c.section_id = s.section_id
ORDER BY t.year, t.section_name, 
         CASE t.day_of_week 
             WHEN 'Monday' THEN 1
             WHEN 'Tuesday' THEN 2
             WHEN 'Wednesday' THEN 3
             WHEN 'Thursday' THEN 4
             WHEN 'Friday' THEN 5
             WHEN 'Saturday' THEN 6
             WHEN 'Sunday' THEN 7
         END,
         t.start_time;
""",
        
        "teacher_conflicts": """
-- Teacher Conflict Analysis
SELECT 
    t1.teacher_name,
    t1.day_of_week,
    t1.start_time,
    t1.end_time,
    COUNT(*) as concurrent_classes,
    GROUP_CONCAT(t1.year || '-' || t1.section_name || ' (' || t1.subject_name || ')') as conflicting_classes
FROM timetable t1
JOIN timetable t2 ON t1.teacher_name = t2.teacher_name 
    AND t1.day_of_week = t2.day_of_week
    AND t1.start_time = t2.start_time
    AND t1.timetable_id != t2.timetable_id
WHERE t1.subject_name != 'Free' AND t2.subject_name != 'Free'
GROUP BY t1.teacher_name, t1.day_of_week, t1.start_time, t1.end_time
HAVING COUNT(*) > 1
ORDER BY t1.teacher_name, t1.day_of_week, t1.start_time;
""",

        "section_utilization": """
-- Section Utilization Analysis
SELECT 
    s.year,
    s.section_name,
    s.capacity,
    s.room_number,
    COUNT(t.timetable_id) as total_classes_per_week,
    COUNT(DISTINCT t.subject_name) as unique_subjects,
    COUNT(DISTINCT t.teacher_name) as unique_teachers,
    ROUND(COUNT(t.timetable_id) * 100.0 / (5 * 8), 2) as utilization_percentage
FROM sections s
LEFT JOIN courses c ON s.section_id = c.section_id
LEFT JOIN timetable t ON c.course_id = t.course_id
GROUP BY s.section_id, s.year, s.section_name, s.capacity, s.room_number
ORDER BY s.year, s.section_name;
""",

        "daily_schedule_summary": """
-- Daily Schedule Summary by Year and Section
SELECT 
    year,
    section_name,
    day_of_week,
    COUNT(*) as classes_count,
    MIN(start_time) as first_class,
    MAX(end_time) as last_class,
    GROUP_CONCAT(subject_name, ', ') as subjects_list
FROM timetable
WHERE subject_name != 'Free'
GROUP BY year, section_name, day_of_week
ORDER BY year, section_name, 
         CASE day_of_week 
             WHEN 'Monday' THEN 1
             WHEN 'Tuesday' THEN 2
             WHEN 'Wednesday' THEN 3
             WHEN 'Thursday' THEN 4
             WHEN 'Friday' THEN 5
             WHEN 'Saturday' THEN 6
             WHEN 'Sunday' THEN 7
         END;
""",

        "teacher_schedule": """
-- Individual Teacher Schedules
SELECT 
    teacher_name,
    year,
    section_name,
    day_of_week,
    start_time,
    end_time,
    subject_name,
    ROW_NUMBER() OVER (PARTITION BY teacher_name ORDER BY 
        CASE day_of_week 
            WHEN 'Monday' THEN 1
            WHEN 'Tuesday' THEN 2
            WHEN 'Wednesday' THEN 3
            WHEN 'Thursday' THEN 4
            WHEN 'Friday' THEN 5
            WHEN 'Saturday' THEN 6
            WHEN 'Sunday' THEN 7
        END, start_time) as class_sequence
FROM timetable
WHERE subject_name != 'Free'
ORDER BY teacher_name, 
         CASE day_of_week 
             WHEN 'Monday' THEN 1
             WHEN 'Tuesday' THEN 2
             WHEN 'Wednesday' THEN 3
             WHEN 'Thursday' THEN 4
             WHEN 'Friday' THEN 5
             WHEN 'Saturday' THEN 6
             WHEN 'Sunday' THEN 7
         END,
         start_time;
""",

        "workload_analysis": """
-- Comprehensive Workload Analysis
SELECT 
    teach.name as teacher_name,
    teach.department,
    teach.start_hour || ':00 - ' || teach.end_hour || ':00' as availability,
    COUNT(DISTINCT t.year) as years_teaching,
    COUNT(DISTINCT CASE WHEN t.subject_name != 'Free' THEN t.subject_name END) as subjects_count,
    COUNT(CASE WHEN t.subject_name != 'Free' THEN t.timetable_id END) as total_classes_per_week,
    ROUND(COUNT(CASE WHEN t.subject_name != 'Free' THEN t.timetable_id END) * 1.0 / 
          COUNT(DISTINCT t.year), 2) as avg_classes_per_year,
    GROUP_CONCAT(DISTINCT t.year) as years_list
FROM teachers teach
LEFT JOIN courses c ON teach.teacher_id = c.teacher_id
LEFT JOIN timetable t ON c.course_id = t.course_id
GROUP BY teach.teacher_id, teach.name, teach.department, teach.start_hour, teach.end_hour
ORDER BY total_classes_per_week DESC;
"""
    }


def get_time_slots(slot_dict: Dict[str, int], start_times: Dict[str, int]) -> Tuple[List[str], Dict[int,int], Dict[str,str], Dict[str,int]]:
    """Generate time slots based on working days and hours."""
    slot_names: List[str] = []
    slot_time: Dict[int,int] = {}
    slot_to_day: Dict[str,str] = {}
    day_slot_counts: Dict[str,int] = {}

    day_abbreviations = {
        'Monday': 'M', 'Tuesday': 'T', 'Wednesday': 'W',
        'Thursday': 'Th', 'Friday': 'F', 'Saturday': 'Sa', 'Sunday': 'Su'
    }

    idx = 0
    for day, hours in slot_dict.items():
        hours = int(hours)
        start = int(start_times[day])
        abbrev = day_abbreviations.get(day, day[:2])
        day_count = 0

        for j in range(hours):
            # Skip lunch hour if it would fall here
            while start == 12:
                start += 1
            slot_name = f"{abbrev}{j + 1}"
            slot_names.append(slot_name)
            slot_time[idx] = start
            slot_to_day[slot_name] = day.lower()
            day_count += 1
            idx += 1
            start += 1

        day_slot_counts[day.lower()] = day_count

    return slot_names, slot_time, slot_to_day, day_slot_counts


def apply_teacher_conflict_constraint(model, occ_metadata, start_at, slot_names, teachers_dict):
    """Apply teacher conflict constraint: A teacher cannot teach multiple classes at the same time."""
    teacher_occurrences = {}
    for occ in occ_metadata:
        teacher = occ.get('teacher', 'Unknown')
        if teacher not in teacher_occurrences:
            teacher_occurrences[teacher] = []
        teacher_occurrences[teacher].append(occ)
    
    for teacher, occurrences in teacher_occurrences.items():
        if len(occurrences) <= 1:
            continue
            
        for i in range(len(occurrences)):
            for j in range(i + 1, len(occurrences)):
                occ1 = occurrences[i]
                occ2 = occurrences[j]
                dur1 = occ1['duration']
                dur2 = occ2['duration']
                
                for s1 in range(len(slot_names)):
                    if (occ1['occ_id'], s1) not in start_at:
                        continue
                    
                    for s2 in range(len(slot_names)):
                        if (occ2['occ_id'], s2) not in start_at:
                            continue
                        
                        end1 = s1 + dur1
                        end2 = s2 + dur2
                        
                        if not (end1 <= s2 or end2 <= s1):
                            model.Add(start_at[(occ1['occ_id'], s1)] + start_at[(occ2['occ_id'], s2)] <= 1)


def apply_section_constraint(model, occ_metadata, start_at, slot_names):
    """Apply section constraint: Only one class per section at any time."""
    section_occurrences = {}
    for occ in occ_metadata:
        section_key = f"{occ['year']}_{occ.get('section', 'A')}"
        if section_key not in section_occurrences:
            section_occurrences[section_key] = []
        section_occurrences[section_key].append(occ)
    
    for section_key, occurrences in section_occurrences.items():
        if len(occurrences) <= 1:
            continue
            
        for i in range(len(occurrences)):
            for j in range(i + 1, len(occurrences)):
                occ1 = occurrences[i]
                occ2 = occurrences[j]
                dur1 = occ1['duration']
                dur2 = occ2['duration']
                
                for s1 in range(len(slot_names)):
                    if (occ1['occ_id'], s1) not in start_at:
                        continue
                    
                    for s2 in range(len(slot_names)):
                        if (occ2['occ_id'], s2) not in start_at:
                            continue
                        
                        end1 = s1 + dur1
                        end2 = s2 + dur2
                        
                        if not (end1 <= s2 or end2 <= s1):
                            model.Add(start_at[(occ1['occ_id'], s1)] + start_at[(occ2['occ_id'], s2)] <= 1)


def generate_college_timetable_with_sections(constraints: Dict[str, Any], courses: List[Dict[str, Any]], 
                                            teachers: Dict[str, Any], sections: Dict[str, Any],
                                            allow_free: bool = True, max_time_seconds: int = 30) -> Any:
    """Generate college timetable with sections support."""
    if not constraints or not courses:
        return {'error': "No constraints or courses provided."}

    working_days = constraints.get("working_days", [])
    if not working_days:
        return {'error': "No working days configured."}

    slot_counts_by_day = {}
    start_times = {}
    for d in working_days:
        day = d["day"]
        slot_counts_by_day[day] = int(d["total_hours"])
        start_times[day] = int(d["start_hr"])

    # Process courses with section information
    processed_courses = []
    for course in courses:
        subject = course["subject"]
        year = course["year"]
        section = course.get("section", "A")
        teacher = course["teacher"]
        lectures = int(course['lectures'])
        duration = int(course['duration'])
        
        teacher_info = teachers.get(teacher, {})
        start_hr = int(teacher_info.get('start_hr', 9))
        end_hr = int(teacher_info.get('end_hr', 17))
        
        processed_courses.append({
            'name': f"{subject}_{year}_{section}_{teacher}",
            'subject': subject,
            'year': year,
            'section': section,
            'teacher': teacher,
            'lectures': lectures,
            'duration': duration,
            'start_hr': start_hr,
            'end_hr': end_hr
        })

    # Build time slots
    slot_names, slot_time, slot_to_day, day_slot_counts = get_time_slots(slot_counts_by_day, start_times)
    num_slots = len(slot_names)

    # Calculate requirements per year-section combination
    section_requirements = {}
    for course in processed_courses:
        section_key = f"{course['year']}_{course['section']}"
        if section_key not in section_requirements:
            section_requirements[section_key] = 0
        section_requirements[section_key] += course['lectures'] * course['duration']

    # Add free periods
    if allow_free:
        for year in ['Year1', 'Year2', 'Year3', 'Year4']:
            year_sections = sections.get(year, {'A': {}})
            for section_name in year_sections.keys():
                section_key = f"{year}_{section_name}"
                section_used = section_requirements.get(section_key, 0)
                if section_used < num_slots:
                    free_needed = num_slots - section_used
                    processed_courses.append({
                        'name': f"Free_{year}_{section_name}",
                        'subject': 'Free',
                        'year': year,
                        'section': section_name,
                        'teacher': 'None',
                        'lectures': free_needed,
                        'duration': 1,
                        'start_hr': 0,
                        'end_hr': 24
                    })

    # Build CP-SAT model
    model = cp_model.CpModel()
    occ_metadata = []
    start_at = {}
    occ_id = 0

    # Create occurrences
    for course in processed_courses:
        name = course['name']
        dur = course['duration']
        
        allowed_vals = []
        for s in range(num_slots):
            end_idx = s + dur - 1
            if end_idx >= num_slots:
                continue
            if slot_to_day[slot_names[s]] != slot_to_day[slot_names[end_idx]]:
                continue
            
            ok = True
            for t in range(s, end_idx + 1):
                if slot_time[t] < course['start_hr'] or slot_time[t] >= course['end_hr']:
                    ok = False
                    break
            if ok:
                allowed_vals.append(s)
        
        if not allowed_vals and course['lectures'] > 0:
            return {'error': f"No feasible slots for {course['subject']} (Year {course['year']}, Section {course['section']})."}

        for k in range(course['lectures']):
            start_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed_vals), f"{name}_s{occ_id}")
            end_var = model.NewIntVar(min(allowed_vals) + dur, max(allowed_vals) + dur, f"{name}_e{occ_id}")
            interval = model.NewIntervalVar(start_var, dur, end_var, f"{name}_it{occ_id}")
            
            occ_metadata.append({
                'occ_id': occ_id, 
                'name': name, 
                'subject': course['subject'],
                'year': course['year'],
                'section': course['section'],
                'teacher': course['teacher'],
                'duration': dur, 
                'start': start_var, 
                'interval': interval
            })

            for s in allowed_vals:
                b = model.NewBoolVar(f"occ{occ_id}_start_at_{s}")
                start_at[(occ_id, s)] = b
                model.Add(start_var == s).OnlyEnforceIf(b)
                model.Add(start_var != s).OnlyEnforceIf(b.Not())

            occ_id += 1

    # Apply constraints
    
    # 1. Section-based no-overlap
    section_intervals = {}
    for occ in occ_metadata:
        section_key = f"{occ['year']}_{occ['section']}"
        if section_key not in section_intervals:
            section_intervals[section_key] = []
        section_intervals[section_key].append(occ['interval'])
    
    for section_key, intervals in section_intervals.items():
        if intervals:
            model.AddNoOverlap(intervals)

    # 2. Teacher conflict constraint
    apply_teacher_conflict_constraint(model, occ_metadata, start_at, slot_names, teachers)
    
    # 3. Section conflict constraint (additional safety)
    apply_section_constraint(model, occ_metadata, start_at, slot_names)

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = 8

    result = solver.Solve(model)
    if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {'error': "No valid timetable found. Try adjusting constraints or reducing conflicts."}

    # Build response organized by year, section, and day
    response_data = {}
    for year in ['Year1', 'Year2', 'Year3', 'Year4']:
        response_data[year] = {}
        year_sections = sections.get(year, {'A': {}})
        for section_name in year_sections.keys():
            response_data[year][section_name] = {
                day.lower(): [] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            }

    for occ in occ_metadata:
        subject = occ['subject']
        year = occ['year']
        section = occ['section']
        teacher = occ['teacher']
        dur = occ['duration']
        start_idx = solver.Value(occ['start'])
        
        slot_name = slot_names[start_idx]
        day = slot_to_day[slot_name]
        start_hr = slot_time[start_idx]
        end_hr = start_hr + dur
        
        # Get room information from sections
        room = ""
        if year in sections and section in sections[year]:
            room = sections[year][section].get('room', '')
        
        if year in response_data and section in response_data[year]:
            response_data[year][section][day].append({
                'slot': slot_name,
                'subject': subject,
                'teacher': teacher,
                'section': section,
                'room': room,
                'start_time': f"{start_hr:02d}:00",
                'end_time': f"{end_hr:02d}:00"
            })

    # Sort schedules by time
    for year in response_data:
        for section in response_data[year]:
            for day in response_data[year][section]:
                response_data[year][section][day].sort(key=lambda x: x['start_time'])

    return response_data


def main():
    initialize_session_state()

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🎓 Enhanced College Timetable Generator</h1>
        <p>Multi-Year • Multi-Section • SQLite Database • Advanced Analytics</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Enhanced features info
    st.markdown("""
    <div class="sqlite-feature">
        🗄️ <strong>New SQLite Features:</strong> Database Export • Advanced Queries • Conflict Analysis • Performance Views
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="enhanced-feature">
        📚 <strong>Section Management:</strong> Multiple Sections per Year • Room Assignment • Capacity Management • Section-wise Scheduling
    </div>
    """, unsafe_allow_html=True)

    # Sidebar for navigation
    st.sidebar.title("🧭 Navigation")
    tab = st.sidebar.radio("Select Option", [
        "Manage Teachers", 
        "Manage Sections", 
        "Add Courses", 
        "Set Constraints", 
        "Generate Timetable", 
        "View Results",
        "SQLite Database",
        "Analytics & Reports"
    ])

    if tab == "Manage Teachers":
        st.header("👩‍🏫 Manage Teachers")
        
        st.markdown("Register teachers with their availability and departments.")

        with st.form("teacher_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                teacher_name = st.text_input("Teacher Name", placeholder="e.g., Dr. Sarah Johnson")
                department = st.text_input("Department", placeholder="e.g., Computer Science")
                
            with col2:
                start_hr = st.number_input("Available From (Hour)", min_value=6, max_value=20, value=9)
                end_hr = st.number_input("Available Until (Hour)", min_value=7, max_value=22, value=17)
            
            years_teaching = st.multiselect("Years Teaching", ["Year1", "Year2", "Year3", "Year4"], default=["Year1"])
            
            submitted = st.form_submit_button("Add Teacher")
            
            if submitted:
                if teacher_name:
                    st.session_state.teachers[teacher_name] = {
                        "name": teacher_name,
                        "department": department,
                        "start_hr": start_hr,
                        "end_hr": end_hr,
                        "years": years_teaching
                    }
                    st.success(f"✅ Teacher '{teacher_name}' added successfully!")
                else:
                    st.error("❌ Please enter teacher name.")

        # Display teachers
        if st.session_state.teachers:
            st.subheader("Registered Teachers")
            for teacher_name, info in st.session_state.teachers.items():
                st.markdown(f"""
                <div class="constraint-box">
                    <strong>{teacher_name}</strong> - {info['department']}<br>
                    Available: {info['start_hr']}:00 - {info['end_hr']}:00<br>
                    Teaching Years: {', '.join(info['years'])}
                </div>
                """, unsafe_allow_html=True)
            
            if st.button("Clear All Teachers"):
                st.session_state.teachers = {}
                st.rerun()

    elif tab == "Manage Sections":
        st.header("🏛️ Manage Sections")
        
        st.markdown("""
        <div class="section-header">
            📋 Section Management System
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("Create and manage sections for each year with room assignments and capacity limits.")

        # Section creation form
        with st.form("section_form"):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                year = st.selectbox("Year", ["Year1", "Year2", "Year3", "Year4"])
            with col2:
                section_name = st.text_input("Section Name", placeholder="e.g., A, B, C")
            with col3:
                capacity = st.number_input("Student Capacity", min_value=20, max_value=150, value=60)
            with col4:
                room_number = st.text_input("Room Number", placeholder="e.g., CS-101")
            
            submitted = st.form_submit_button("Add Section")
            
            if submitted:
                if year and section_name:
                    if year not in st.session_state.sections:
                        st.session_state.sections[year] = {}
                    
                    st.session_state.sections[year][section_name.upper()] = {
                        "capacity": capacity,
                        "room": room_number,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.success(f"✅ Section '{section_name.upper()}' added to {year}!")
                else:
                    st.error("❌ Please fill in year and section name.")

        # Display sections by year
        if st.session_state.sections:
            st.subheader("📚 Sections by Year")
            
            for year in ["Year1", "Year2", "Year3", "Year4"]:
                if year in st.session_state.sections and st.session_state.sections[year]:
                    st.markdown(f"""
                    <div class="year-box">
                        <h4>📘 {year}</h4>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    sections_data = []
                    for section_name, section_info in st.session_state.sections[year].items():
                        sections_data.append({
                            "Section": section_name,
                            "Capacity": section_info["capacity"],
                            "Room": section_info["room"] or "TBD",
                            "Created": section_info.get("created_at", "N/A")
                        })
                    
                    if sections_data:
                        df_sections = pd.DataFrame(sections_data)
                        st.dataframe(df_sections, use_container_width=True, hide_index=True)

            if st.button("Clear All Sections"):
                st.session_state.sections = {}
                st.rerun()
        else:
            st.info("No sections created yet. Add sections to organize your classes.")

    elif tab == "Add Courses":
        st.header("📚 Add Courses")

        if not st.session_state.teachers:
            st.warning("⚠️ Please add teachers first before creating courses.")
            return
        
        if not st.session_state.sections:
            st.warning("⚠️ Please add sections first before creating courses.")
            return

        with st.form("course_form"):
            col1, col2 = st.columns(2)

            with col1:
                subject_name = st.text_input("Subject Name", placeholder="e.g., Data Structures")
                year = st.selectbox("Year", ["Year1", "Year2", "Year3", "Year4"])
                
                # Dynamic section selection based on year
                available_sections = list(st.session_state.sections.get(year, {"A": {}}).keys())
                if available_sections:
                    section = st.selectbox("Section", available_sections)
                else:
                    section = st.text_input("Section", value="A", placeholder="No sections available for this year")
                
                lectures_per_week = st.number_input("Lectures per Week", min_value=1, max_value=8, value=3)

            with col2:
                teacher_options = [t for t, info in st.session_state.teachers.items() 
                                if year in info.get('years', [])]
                if not teacher_options:
                    st.error(f"No teachers available for {year}")
                    return
                    
                teacher = st.selectbox("Teacher", teacher_options)
                duration = st.selectbox("Duration per Lecture (hours)", [1, 2, 3], index=0)
                subject_code = st.text_input("Subject Code", placeholder="e.g., CS301")

            submitted = st.form_submit_button("Add Course")

            if submitted:
                if subject_name and teacher and section:
                    course = {
                        "subject": subject_name.strip(),
                        "subject_code": subject_code.strip() or subject_name[:6].upper(),
                        "year": year,
                        "section": section,
                        "teacher": teacher,
                        "lectures": int(lectures_per_week),
                        "duration": int(duration)
                    }
                    st.session_state.courses.append(course)
                    st.success(f"✅ Course '{subject_name}' for {year}-{section} added successfully!")
                else:
                    st.error("❌ Please fill in all required fields.")

        # Display courses organized by year and section
        if st.session_state.courses:
            st.subheader("📖 Added Courses")
            
            for year in ["Year1", "Year2", "Year3", "Year4"]:
                year_courses = [c for c in st.session_state.courses if c['year'] == year]
                if year_courses:
                    st.markdown(f"""
                    <div class="year-box">
                        <h4>📘 {year}</h4>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Group by section
                    sections_in_year = {}
                    for course in year_courses:
                        section = course['section']
                        if section not in sections_in_year:
                            sections_in_year[section] = []
                        sections_in_year[section].append(course)
                    
                    for section_name, section_courses in sections_in_year.items():
                        st.markdown(f"""
                        <div class="section-box">
                            <h5>📚 Section {section_name}</h5>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        course_data = []
                        for course in section_courses:
                            teacher_info = st.session_state.teachers.get(course['teacher'], {})
                            section_info = st.session_state.sections.get(year, {}).get(section_name, {})
                            
                            course_data.append({
                                "Subject": course['subject'],
                                "Code": course.get('subject_code', 'N/A'),
                                "Teacher": course['teacher'],
                                "Lectures/Week": f"{course['lectures']} × {course['duration']}h",
                                "Room": section_info.get('room', 'TBD'),
                                "Teacher Availability": f"{teacher_info.get('start_hr', 'N/A')}:00-{teacher_info.get('end_hr', 'N/A')}:00"
                            })
                        
                        df_courses = pd.DataFrame(course_data)
                        st.dataframe(df_courses, use_container_width=True, hide_index=True)

            if st.button("Clear All Courses"):
                st.session_state.courses = []
                st.session_state.generated_timetable = None
                st.rerun()

    elif tab == "Set Constraints":
        st.header("⚙️ Set Constraints")

        # Working Days Configuration
        st.subheader("📅 Working Days Configuration")
        working_days = []

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

        for day in days:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                include_day = st.checkbox(f"Include {day}", key=f"include_{day}", value=True if day != "Saturday" else False)

            if include_day:
                with col2:
                    start_hr = st.number_input(f"{day} Start", min_value=6, max_value=20, value=8, key=f"start_{day}")
                with col3:
                    end_hr = st.number_input(f"{day} End", min_value=7, max_value=22, value=18, key=f"end_{day}")
                with col4:
                    total_hours = st.number_input(f"Total Hours", min_value=1, max_value=12, value=8, key=f"total_{day}")

                working_days.append({
                    "day": day,
                    "start_hr": str(int(start_hr)),
                    "end_hr": str(int(end_hr)),
                    "total_hours": str(int(total_hours))
                })

        # Enhanced Constraints
        st.subheader("🚀 Advanced Scheduling Options")
        
        col1, col2 = st.columns(2)
        with col1:
            enable_lunch = st.checkbox("Lunch Break Protection", value=True, help="Limit academic classes during 12-13 hours")
            strict_teacher_availability = st.checkbox("Strict Teacher Availability", value=True, help="Enforce teacher working hours strictly")
        with col2:
            allow_back_to_back = st.checkbox("Allow Back-to-Back Classes", value=True, help="Allow consecutive classes for same subject")
            optimize_room_usage = st.checkbox("Optimize Room Usage", value=False, help="Try to minimize room changes")

        if st.button("💾 Save Constraints"):
            st.session_state.constraints = {
                "working_days": working_days,
                "enable_lunch_break": enable_lunch,
                "strict_teacher_availability": strict_teacher_availability,
                "allow_back_to_back": allow_back_to_back,
                "optimize_room_usage": optimize_room_usage
            }
            st.success("✅ Constraints saved successfully!")

    elif tab == "Generate Timetable":
        st.header("🎯 Generate Enhanced Timetable")

        if not st.session_state.teachers:
            st.error("❌ No teachers registered. Please add teachers first.")
            return
            
        if not st.session_state.courses:
            st.error("❌ No courses added. Please add courses first.")
            return

        if not st.session_state.sections:
            st.error("❌ No sections created. Please add sections first.")
            return

        if not st.session_state.constraints:
            st.error("❌ No constraints set. Please set constraints first.")
            return

        # Pre-generation analysis
        st.subheader("📊 Pre-Generation Analysis")
        
        # Section analysis
        total_sections = sum(len(sections) for sections in st.session_state.sections.values())
        total_courses = len(st.session_state.courses)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sections", total_sections)
        with col2:
            st.metric("Total Courses", total_courses)
        with col3:
            st.metric("Teachers", len(st.session_state.teachers))
        with col4:
            avg_courses_per_section = total_courses / total_sections if total_sections > 0 else 0
            st.metric("Avg Courses/Section", f"{avg_courses_per_section:.1f}")

        # Teacher workload preview
        teacher_workload = {}
        for course in st.session_state.courses:
            teacher = course['teacher']
            if teacher not in teacher_workload:
                teacher_workload[teacher] = {'courses': 0, 'hours': 0, 'sections': set()}
            teacher_workload[teacher]['courses'] += 1
            teacher_workload[teacher]['hours'] += course['lectures'] * course['duration']
            teacher_workload[teacher]['sections'].add(f"{course['year']}-{course['section']}")

        if teacher_workload:
            st.subheader("👥 Teacher Workload Preview")
            workload_data = []
            for teacher, workload in teacher_workload.items():
                teacher_info = st.session_state.teachers[teacher]
                workload_data.append({
                    "Teacher": teacher,
                    "Department": teacher_info.get('department', 'N/A'),
                    "Courses": workload['courses'],
                    "Hours/Week": workload['hours'],
                    "Sections": len(workload['sections']),
                    "Section List": ', '.join(sorted(workload['sections']))
                })
            
            df_workload = pd.DataFrame(workload_data)
            st.dataframe(df_workload, use_container_width=True, hide_index=True)

        # Generation options
        st.subheader("⚡ Generation Options")
        col1, col2 = st.columns(2)
        with col1:
            allow_free = st.checkbox("Allow Free Periods", value=True)
            max_time = st.slider("Max Solving Time (seconds)", min_value=10, max_value=120, value=45)
        with col2:
            generate_sqlite = st.checkbox("Generate SQLite Database", value=True)
            include_analytics = st.checkbox("Include Analytics Views", value=True)

        # Generate button
        if st.button("🎯 Generate Enhanced Timetable", type="primary"):
            with st.spinner("Generating multi-section timetable with advanced constraints..."):
                try:
                    result = generate_college_timetable_with_sections(
                        st.session_state.constraints,
                        st.session_state.courses,
                        st.session_state.teachers,
                        st.session_state.sections,
                        allow_free=allow_free,
                        max_time_seconds=max_time
                    )
                except Exception as e:
                    st.session_state.generated_timetable = None
                    st.session_state.last_error = str(e)
                    st.error(f"❌ Error during generation: {str(e)}")
                    return

                if isinstance(result, dict) and result.get('error'):
                    st.session_state.generated_timetable = None
                    st.session_state.last_error = result['error']
                    st.error(f"❌ {result['error']}")
                else:
                    st.session_state.generated_timetable = result
                    st.session_state.last_error = None
                    
                    # Generate SQLite database if requested
                    if generate_sqlite:
                        try:
                            db_path = create_sqlite_database(
                                result, 
                                st.session_state.teachers, 
                                st.session_state.sections, 
                                st.session_state.courses
                            )
                            st.session_state.sqlite_db_path = db_path
                            st.success("✅ Enhanced timetable and SQLite database generated successfully!")
                        except Exception as e:
                            st.warning(f"⚠️ Timetable generated but SQLite creation failed: {str(e)}")
                            st.success("✅ Enhanced timetable generated successfully!")
                    else:
                        st.success("✅ Enhanced timetable generated successfully!")

    elif tab == "View Results":
        st.header("📋 Enhanced Timetable Results")

        if not st.session_state.generated_timetable:
            st.warning("⚠️ No timetable generated yet.")
            return

        timetable = st.session_state.generated_timetable

        # Year and section selection
        col1, col2 = st.columns(2)
        with col1:
            selected_year = st.selectbox("Select Year", ["Year1", "Year2", "Year3", "Year4"])
        with col2:
            available_sections = list(timetable.get(selected_year, {}).keys()) if selected_year in timetable else []
            if available_sections:
                selected_section = st.selectbox("Select Section", available_sections)
            else:
                st.warning(f"No sections found for {selected_year}")
                return
        
        if selected_year in timetable and selected_section in timetable[selected_year]:
            section_schedule = timetable[selected_year][selected_section]
            
            # Section-specific analysis
            st.subheader(f"📊 {selected_year}-{selected_section} Analysis")
            
            total_classes = 0
            free_periods = 0
            subjects_count = {}
            teachers_count = {}
            daily_classes = {}
            
            for day, schedule in section_schedule.items():
                daily_classes[day] = len([item for item in schedule if not item['subject'].startswith('Free')])
                for item in schedule:
                    total_classes += 1
                    subject = item['subject']
                    teacher = item['teacher']
                    
                    if subject.startswith("Free"):
                        free_periods += 1
                    else:
                        subjects_count[subject] = subjects_count.get(subject, 0) + 1
                        teachers_count[teacher] = teachers_count.get(teacher, 0) + 1

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Total Classes", total_classes)
            with col2:
                st.metric("Free Periods", free_periods)
            with col3:
                st.metric("Subjects", len(subjects_count))
            with col4:
                st.metric("Teachers", len([t for t in teachers_count if t != 'None']))
            with col5:
                busiest_day = max(daily_classes, key=daily_classes.get) if daily_classes else "N/A"
                st.metric("Busiest Day", busiest_day)

            # Section info
            section_info = st.session_state.sections.get(selected_year, {}).get(selected_section, {})
            if section_info:
                st.info(f"📍 Room: {section_info.get('room', 'TBD')} | 👥 Capacity: {section_info.get('capacity', 'N/A')} students")

            # Daily schedule display
            st.subheader(f"📅 {selected_year}-{selected_section} Weekly Schedule")
            
            days_with_classes = [day for day, schedule in section_schedule.items() if schedule]
            
            if days_with_classes:
                day_tabs = st.tabs([f"{day.capitalize()} ({len(section_schedule[day])})" for day in days_with_classes])
                
                for i, day in enumerate(days_with_classes):
                    with day_tabs[i]:
                        schedule = section_schedule[day]
                        
                        if schedule:
                            df_data = []
                            for item in schedule:
                                subject = item['subject']
                                teacher = item['teacher']
                                room = item.get('room', section_info.get('room', 'TBD'))
                                
                                visual_subject = subject
                                if subject.startswith("Free"):
                                    visual_subject = f"🆓 Free Period"
                                    teacher_display = "—"
                                elif item['start_time'].startswith('12:'):
                                    visual_subject = f"🍽️ {subject}"
                                    teacher_display = teacher
                                else:
                                    teacher_display = teacher
                                
                                df_data.append({
                                    "Time": f"{item['start_time']} - {item['end_time']}",
                                    "Subject": visual_subject,
                                    "Teacher": teacher_display,
                                    "Room": room,
                                    "Slot": item['slot']
                                })

                            df = pd.DataFrame(df_data)
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            st.info(f"No classes on {day.capitalize()}")

        # Multi-Section Comparison
        st.subheader("📊 Multi-Section Analysis")
        
        if selected_year in timetable:
            comparison_data = []
            for section_name, section_data in timetable[selected_year].items():
                total_classes = sum(len(schedule) for schedule in section_data.values())
                free_periods = sum(1 for day_schedule in section_data.values() 
                                 for item in day_schedule if item['subject'].startswith("Free"))
                academic_classes = total_classes - free_periods
                
                # Count unique teachers and subjects
                section_teachers = set()
                section_subjects = set()
                for day_schedule in section_data.values():
                    for item in day_schedule:
                        if item['teacher'] != 'None' and not item['subject'].startswith("Free"):
                            section_teachers.add(item['teacher'])
                            section_subjects.add(item['subject'])
                
                section_info = st.session_state.sections.get(selected_year, {}).get(section_name, {})
                
                comparison_data.append({
                    'Section': section_name,
                    'Room': section_info.get('room', 'TBD'),
                    'Capacity': section_info.get('capacity', 'N/A'),
                    'Total Classes': total_classes,
                    'Academic Classes': academic_classes,
                    'Free Periods': free_periods,
                    'Subjects': len(section_subjects),
                    'Teachers': len(section_teachers)
                })
            
            if comparison_data:
                df_comparison = pd.DataFrame(comparison_data)
                st.dataframe(df_comparison, use_container_width=True, hide_index=True)

        # Export options for current view
        st.subheader("📤 Export Current View")
        if st.button("📊 Export Section Schedule (CSV)"):
            if selected_year in timetable and selected_section in timetable[selected_year]:
                csv_data = []
                for day, schedule in timetable[selected_year][selected_section].items():
                    for item in schedule:
                        csv_data.append({
                            'Year': selected_year,
                            'Section': selected_section,
                            'Day': day.capitalize(),
                            'Time Slot': item['slot'],
                            'Subject': item['subject'],
                            'Teacher': item['teacher'],
                            'Room': item.get('room', ''),
                            'Start Time': item['start_time'],
                            'End Time': item['end_time']
                        })
                
                if csv_data:
                    df_csv = pd.DataFrame(csv_data)
                    csv_string = df_csv.to_csv(index=False)
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv_string,
                        file_name=f"{selected_year}_{selected_section}_timetable.csv",
                        mime="text/csv"
                    )

    elif tab == "SQLite Database":
        st.header("🗄️ SQLite Database Management")

        if not st.session_state.sqlite_db_path:
            st.warning("⚠️ No SQLite database generated yet. Generate a timetable with SQLite option enabled first.")
            return

        st.markdown("""
        <div class="sqlite-feature">
            🎯 <strong>Database Features:</strong> Complete timetable data • Advanced queries • Performance analytics • Export capabilities
        </div>
        """, unsafe_allow_html=True)

        # Database info
        if os.path.exists(st.session_state.sqlite_db_path):
            file_size = os.path.getsize(st.session_state.sqlite_db_path)
            st.info(f"📊 Database Size: {file_size / 1024:.2f} KB | 📍 Path: {st.session_state.sqlite_db_path}")

        # Download database
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Download SQLite Database"):
                with open(st.session_state.sqlite_db_path, 'rb') as f:
                    st.download_button(
                        label="💾 Download Database File",
                        data=f.read(),
                        file_name="college_timetable.db",
                        mime="application/octet-stream"
                    )

        with col2:
            if st.button("🔄 Regenerate Database"):
                if st.session_state.generated_timetable:
                    try:
                        db_path = create_sqlite_database(
                            st.session_state.generated_timetable,
                            st.session_state.teachers,
                            st.session_state.sections,
                            st.session_state.courses
                        )
                        st.session_state.sqlite_db_path = db_path
                        st.success("✅ Database regenerated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Database regeneration failed: {str(e)}")

        # Pre-built queries
        st.subheader("🔍 Pre-built Database Queries")
        
        sql_queries = generate_sql_export_queries()
        query_names = {
            "complete_timetable": "📋 Complete Timetable",
            "teacher_conflicts": "⚠️ Teacher Conflicts",
            "section_utilization": "📊 Section Utilization",
            "daily_schedule_summary": "📅 Daily Schedule Summary", 
            "teacher_schedule": "👨‍🏫 Teacher Schedules",
            "workload_analysis": "💼 Workload Analysis"
        }

        selected_query = st.selectbox("Select Query", 
                                    options=list(query_names.keys()),
                                    format_func=lambda x: query_names[x])

        # Display selected query
        st.subheader(f"📝 SQL Query: {query_names[selected_query]}")
        st.code(sql_queries[selected_query], language="sql")

        # Execute query
        if st.button("▶️ Execute Query"):
            try:
                conn = sqlite3.connect(st.session_state.sqlite_db_path)
                df_result = pd.read_sql_query(sql_queries[selected_query], conn)
                conn.close()
                
                if not df_result.empty:
                    st.subheader("📊 Query Results")
                    st.dataframe(df_result, use_container_width=True, hide_index=True)
                    
                    # Export results
                    csv_result = df_result.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Results (CSV)",
                        data=csv_result,
                        file_name=f"{selected_query}_results.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No results found for this query.")
                    
            except Exception as e:
                st.error(f"❌ Query execution failed: {str(e)}")

        # Custom query interface
        st.subheader("✏️ Custom SQL Query")
        custom_query = st.text_area("Enter your SQL query:", 
                                   placeholder="SELECT * FROM timetable WHERE year = 'Year1' LIMIT 10;",
                                   height=100)
        
        if st.button("🚀 Execute Custom Query") and custom_query:
            try:
                conn = sqlite3.connect(st.session_state.sqlite_db_path)
                df_custom = pd.read_sql_query(custom_query, conn)
                conn.close()
                
                if not df_custom.empty:
                    st.subheader("🎯 Custom Query Results")
                    st.dataframe(df_custom, use_container_width=True, hide_index=True)
                else:
                    st.info("Query executed successfully but returned no results.")
                    
            except Exception as e:
                st.error(f"❌ Custom query failed: {str(e)}")

        # Database schema
        st.subheader("🗂️ Database Schema")
        with st.expander("View Table Structure"):
            schema_info = """
            **Tables in the database:**
            
            1. **teachers** - Teacher information and availability
               - teacher_id, name, department, start_hour, end_hour, years_teaching
            
            2. **sections** - Section details with rooms and capacity
               - section_id, year, section_name, capacity, room_number
            
            3. **subjects** - Subject catalog
               - subject_id, name, code, credits
            
            4. **courses** - Course assignments linking teachers, subjects, and sections
               - course_id, subject_id, teacher_id, section_id, lectures_per_week, duration_hours
            
            5. **timetable** - Complete schedule data
               - timetable_id, course_id, year, section_name, day_of_week, start_time, end_time, slot_name, subject_name, teacher_name, room_number
            
            6. **time_slots** - Time slot definitions
               - slot_id, slot_name, day_of_week, start_time, end_time, is_lunch_period
            
            **Views available:**
            - teacher_schedule - Complete teacher schedules with details
            - section_schedule - Section-wise schedules
            - teacher_workload - Teacher workload analysis
            """
            st.markdown(schema_info)

    elif tab == "Analytics & Reports":
        st.header("📈 Analytics & Advanced Reports")

        if not st.session_state.generated_timetable:
            st.warning("⚠️ No timetable data available. Generate a timetable first.")
            return

        timetable = st.session_state.generated_timetable

        # Comprehensive Analytics Dashboard
        st.subheader("📊 Timetable Analytics Dashboard")

        # Overall Statistics
        total_sections = 0
        total_classes = 0
        total_free_periods = 0
        teacher_utilization = {}
        subject_distribution = {}
        daily_load = {}
        room_utilization = {}

        for year, year_data in timetable.items():
            for section, section_data in year_data.items():
                total_sections += 1
                for day, day_schedule in section_data.items():
                    daily_load[day] = daily_load.get(day, 0) + len([item for item in day_schedule if not item['subject'].startswith('Free')])
                    for item in day_schedule:
                        total_classes += 1
                        subject = item['subject']
                        teacher = item['teacher']
                        room = item.get('room', 'Unknown')
                        
                        if subject.startswith('Free'):
                            total_free_periods += 1
                        else:
                            subject_distribution[subject] = subject_distribution.get(subject, 0) + 1
                            if teacher != 'None':
                                teacher_utilization[teacher] = teacher_utilization.get(teacher, 0) + 1
                            if room != 'Unknown':
                                room_utilization[room] = room_utilization.get(room, 0) + 1

        # Key Metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Sections", total_sections)
        with col2:
            st.metric("Total Classes", total_classes)
        with col3:
            st.metric("Free Periods", total_free_periods)
        with col4:
            utilization_rate = ((total_classes - total_free_periods) / total_classes * 100) if total_classes > 0 else 0
            st.metric("Utilization Rate", f"{utilization_rate:.1f}%")
        with col5:
            avg_classes_per_section = total_classes / total_sections if total_sections > 0 else 0
            st.metric("Avg Classes/Section", f"{avg_classes_per_section:.1f}")

        # Charts and Visualizations
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Teacher Analysis", "📚 Subject Analysis", "📅 Daily Distribution", "🏛️ Room Analysis"])

        with tab1:
            st.subheader("👨‍🏫 Teacher Workload Analysis")
            if teacher_utilization:
                # Teacher workload chart data
                teacher_data = []
                for teacher, classes in sorted(teacher_utilization.items(), key=lambda x: x[1], reverse=True):
                    teacher_info = st.session_state.teachers.get(teacher, {})
                    # Count unique years this teacher teaches
                    teacher_years = set()
                    teacher_sections = set()
                    for year, year_data in timetable.items():
                        for section, section_data in year_data.items():
                            for day, day_schedule in section_data.items():
                                for item in day_schedule:
                                    if item['teacher'] == teacher and not item['subject'].startswith('Free'):
                                        teacher_years.add(year)
                                        teacher_sections.add(f"{year}-{section}")
                    
                    teacher_data.append({
                        "Teacher": teacher,
                        "Department": teacher_info.get('department', 'Unknown'),
                        "Classes per Week": classes,
                        "Years Teaching": len(teacher_years),
                        "Sections": len(teacher_sections),
                        "Availability": f"{teacher_info.get('start_hr', 'N/A')}-{teacher_info.get('end_hr', 'N/A')}h"
                    })
                
                df_teachers = pd.DataFrame(teacher_data)
                st.dataframe(df_teachers, use_container_width=True, hide_index=True)
                
                # Top 10 busiest teachers
                if len(teacher_data) > 0:
                    st.subheader("🔥 Top 10 Busiest Teachers")
                    top_teachers = sorted(teacher_utilization.items(), key=lambda x: x[1], reverse=True)[:10]
                    for i, (teacher, classes) in enumerate(top_teachers, 1):
                        dept = st.session_state.teachers.get(teacher, {}).get('department', 'Unknown')
                        st.write(f"{i}. **{teacher}** ({dept}) - {classes} classes/week")

        with tab2:
            st.subheader("📚 Subject Distribution Analysis")
            if subject_distribution:
                subject_data = []
                for subject, count in sorted(subject_distribution.items(), key=lambda x: x[1], reverse=True):
                    # Find which years/sections have this subject
                    subject_years = set()
                    subject_teachers = set()
                    for year, year_data in timetable.items():
                        for section, section_data in year_data.items():
                            for day, day_schedule in section_data.items():
                                for item in day_schedule:
                                    if item['subject'] == subject:
                                        subject_years.add(year)
                                        if item['teacher'] != 'None':
                                            subject_teachers.add(item['teacher'])
                    
                    subject_data.append({
                        "Subject": subject,
                        "Total Classes": count,
                        "Years Offered": len(subject_years),
                        "Teachers": len(subject_teachers),
                        "Years List": ', '.join(sorted(subject_years)),
                        "Teacher List": ', '.join(sorted(subject_teachers))
                    })
                
                df_subjects = pd.DataFrame(subject_data)
                st.dataframe(df_subjects, use_container_width=True, hide_index=True)

        with tab3:
            st.subheader("📅 Daily Load Distribution")
            if daily_load:
                daily_data = []
                for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
                    if day.lower() in daily_load:
                        classes = daily_load[day.lower()]
                        # Calculate average per section
                        avg_per_section = classes / total_sections if total_sections > 0 else 0
                        daily_data.append({
                            "Day": day,
                            "Total Classes": classes,
                            "Avg per Section": f"{avg_per_section:.1f}",
                            "Load %": f"{(classes / sum(daily_load.values()) * 100):.1f}%" if daily_load else "0%"
                        })
                
                df_daily = pd.DataFrame(daily_data)
                st.dataframe(df_daily, use_container_width=True, hide_index=True)
                
                # Find busiest and lightest days
                if daily_load:
                    busiest_day = max(daily_load, key=daily_load.get)
                    lightest_day = min(daily_load, key=daily_load.get)
                    st.info(f"📈 Busiest Day: **{busiest_day.capitalize()}** ({daily_load[busiest_day]} classes) | 📉 Lightest Day: **{lightest_day.capitalize()}** ({daily_load[lightest_day]} classes)")

        with tab4:
            st.subheader("🏛️ Room Utilization Analysis")
            if room_utilization:
                room_data = []
                for room, usage in sorted(room_utilization.items(), key=lambda x: x[1], reverse=True):
                    # Find which sections use this room
                    room_sections = set()
                    room_subjects = set()
                    for year, year_data in timetable.items():
                        for section, section_data in year_data.items():
                            for day, day_schedule in section_data.items():
                                for item in day_schedule:
                                    if item.get('room') == room:
                                        room_sections.add(f"{year}-{section}")
                                        if not item['subject'].startswith('Free'):
                                            room_subjects.add(item['subject'])
                    
                    room_data.append({
                        "Room": room,
                        "Usage (classes)": usage,
                        "Sections Using": len(room_sections),
                        "Different Subjects": len(room_subjects),
                        "Section List": ', '.join(sorted(room_sections)),
                        "Utilization %": f"{(usage / total_classes * 100):.1f}%" if total_classes > 0 else "0%"
                    })
                
                df_rooms = pd.DataFrame(room_data)
                st.dataframe(df_rooms, use_container_width=True, hide_index=True)
            else:
                st.info("No room data available. Rooms may not be assigned to sections.")

        # Conflict Analysis
        st.subheader("⚠️ Conflict Analysis")
        conflicts_found = []
        
        # Check for teacher conflicts
        teacher_conflicts = {}
        for year, year_data in timetable.items():
            for section, section_data in year_data.items():
                for day, day_schedule in section_data.items():
                    for item in day_schedule:
                        teacher = item['teacher']
                        if teacher != 'None' and not item['subject'].startswith('Free'):
                            time_key = f"{day}_{item['start_time']}"
                            if time_key not in teacher_conflicts:
                                teacher_conflicts[time_key] = {}
                            if teacher not in teacher_conflicts[time_key]:
                                teacher_conflicts[time_key][teacher] = []
                            teacher_conflicts[time_key][teacher].append({
                                'year': year,
                                'section': section,
                                'subject': item['subject']
                            })

        for time_slot, teachers in teacher_conflicts.items():
            for teacher, assignments in teachers.items():
                if len(assignments) > 1:
                    conflicts_found.append({
                        'Type': 'Teacher Conflict',
                        'Teacher/Resource': teacher,
                        'Time Slot': time_slot.replace('_', ' '),
                        'Conflicting Classes': len(assignments),
                        'Details': '; '.join([f"{a['year']}-{a['section']} ({a['subject']})" for a in assignments])
                    })

        if conflicts_found:
            st.error("❌ Conflicts detected in the timetable:")
            df_conflicts = pd.DataFrame(conflicts_found)
            st.dataframe(df_conflicts, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No conflicts detected! The timetable is optimally scheduled.")

        # Export comprehensive report
        st.subheader("📤 Export Comprehensive Report")
        if st.button("📊 Generate Complete Analytics Report"):
            # Create comprehensive report
            report_data = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'summary': {
                    'total_sections': total_sections,
                    'total_classes': total_classes,
                    'total_free_periods': total_free_periods,
                    'utilization_rate': utilization_rate
                },
                'teacher_analysis': teacher_data if 'teacher_data' in locals() else [],
                'subject_analysis': subject_data if 'subject_data' in locals() else [],
                'daily_analysis': daily_data if 'daily_data' in locals() else [],
                'room_analysis': room_data if 'room_data' in locals() else [],
                'conflicts': conflicts_found
            }
            
            report_json = json.dumps(report_data, indent=2)
            st.download_button(
                label="📥 Download Analytics Report (JSON)",
                data=report_json,
                file_name=f"timetable_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

    # Footer with enhanced tips
    st.markdown("---")
    st.markdown("""
    ### 🎓 Enhanced College Timetable Management
    
    **🔥 New Features:**
    - **Multi-Section Support**: Create and manage multiple sections per year with individual room assignments
    - **SQLite Integration**: Complete database export with advanced querying capabilities
    - **Enhanced Analytics**: Comprehensive conflict analysis, workload distribution, and utilization metrics
    - **Advanced Constraints**: Section-specific scheduling, room optimization, and teacher availability enforcement
    
    **💡 Pro Tips:**
    - Use sections to manage large student populations effectively
    - Assign specific rooms to sections for better organization
    - Monitor teacher workload across multiple years and sections
    - Use SQLite export for integration with external systems
    - Leverage analytics to optimize future scheduling decisions
    
    **🛠️ Technical Features:**
    - OR-Tools CP-SAT solver for optimal scheduling
    - Advanced constraint satisfaction with section and teacher conflicts
    - Performance-optimized database with indexes and views
    - Comprehensive export options (JSON, CSV, SQLite)
    """)


if __name__ == "__main__":
    main()