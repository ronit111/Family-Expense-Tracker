# Expense Tracker Web App (Step 1)
# This is the main Flask application file.
# For now, it just shows a simple welcome page.
# We'll expand it step by step!

from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import logging
import json  # For saving/loading data
import os    # For checking file existence

# Set up logging for debugging and production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s',
    handlers=[
        logging.FileHandler("expense_tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Global currency setting
default_currency = "INR"
currency = default_currency

# --- Persistent storage setup ---
# File paths for data persistence
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
EXPENSES_FILE = os.path.join(DATA_DIR, 'expenses.json')
BUDGETS_FILE = os.path.join(DATA_DIR, 'budgets.json')
INDIVIDUALS_FILE = os.path.join(DATA_DIR, 'individuals.json')

# Helper functions to load and save data

def load_json(filename, default):
    """Load JSON data from a file or return default if file does not exist."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load {filename}: {e}")
            return default
    return default

def save_json(filename, data):
    """Save data as JSON to a file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save {filename}: {e}")

# --- Load data at startup ---
import uuid
individuals = load_json(INDIVIDUALS_FILE, [])  # List of people
expenses = load_json(EXPENSES_FILE, [])        # List of expenses
budgets = load_json(BUDGETS_FILE, {})          # Budgets and incomes by month

# FORCE MIGRATION: Add a unique ID to every expense and exit after saving
for exp in expenses:
    if 'id' not in exp:
        exp['id'] = str(uuid.uuid4())
save_json(EXPENSES_FILE, expenses)

app = Flask(__name__)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    global individuals, currency, budgets
    message = None
    status = 'success'
    if request.method == 'POST':
        # Update individuals
        if 'individuals' in request.form:
            names = [n.strip() for n in request.form.get('individuals', '').split(',') if n.strip()]
            if names:
                individuals = names
                save_json(INDIVIDUALS_FILE, individuals)  # Save updated people
                # Initialize budgets for new individuals
                for month, entries in budgets.items():
                    for name in names:
                        if not any(name in entry['people'] for entry in entries):
                            entries.append({'people': [name], 'income': 0, 'budget': 0})
                save_json(BUDGETS_FILE, budgets)  # Save updated budgets
                message = 'Updated persons.'
            else:
                status = 'error'
                message = 'No valid names provided.'
        # Update currency
        if 'currency' in request.form:
            new_currency = request.form.get('currency', default_currency)
            currency = new_currency
            message = 'Updated currency.'
            # (Currency is not persisted, but you can add similar logic if desired)
        # Detect AJAX (fetch) request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify
            return jsonify({'status': status, 'message': message})
    return render_template('settings_modal.html', individuals=individuals, currency=currency, message=message, status=status)

# --- Income route for adding/updating incomes ---
@app.route('/income', methods=['POST'])
def save_income():
    global budgets
    from flask import jsonify
    status = 'success'
    message = 'Income saved.'
    # Detect JSON AJAX (new logic)
    if request.is_json:
        data = request.get_json()
        month = data.get('month')
        person = data.get('person')
        try:
            income_val = float(data.get('income', 0))
        except (ValueError, TypeError):
            income_val = 0
        # Update or add entry for this person/month
        found = False
        for entry in budgets.setdefault(month, []):
            if person in entry['people']:
                entry['income'] = income_val
                found = True
        if not found:
            budgets[month].append({'people': [person], 'income': income_val, 'budget': 0})
        save_json(BUDGETS_FILE, budgets)  # Save after updating income
        return jsonify({'status': status, 'income': income_val})
    # Legacy form POST (bulk update)
    month = request.form.get('month')
    for person in individuals:
        income_val = request.form.get(f'income_{person}', None)
        if income_val is not None:
            try:
                income_val = float(income_val)
            except ValueError:
                income_val = 0
            found = False
            for entry in budgets.setdefault(month, []):
                if person in entry['people']:
                    entry['income'] = income_val
                    found = True
            if not found:
                budgets[month].append({'people': [person], 'income': income_val, 'budget': 0})
        save_json(BUDGETS_FILE, budgets)  # Save after updating income
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': status, 'message': message})
    return redirect(url_for('income_tab'))

@app.route('/delete_all', methods=['POST'])
def delete_all():
    """
    Deletes all expenses, budgets, investments, and persons (individuals), and resets currency.
    """
    global individuals, currency, budgets, expenses, investments
    individuals = []  # Clear all persons
    currency = default_currency
    budgets = {}
    expenses = []
    investments = {}
    save_json(EXPENSES_FILE, expenses)
    save_json(BUDGETS_FILE, budgets)
    save_json(INDIVIDUALS_FILE, individuals)
    # Optionally, save investments if you persist them
    # save_json(INVESTMENTS_FILE, investments)
    return redirect(url_for('home'))

# Redirect root URL to expenses page
@app.route('/')
def home_redirect():
    print("Home route triggered")
    return redirect(url_for('expenses_tab'))

# --- Analytics Route: Shows MoM bar charts for expenses and incomes ---
# --- Helper: Get per-person expense shares (including 'All') ---
def get_person_expenses(person, expenses, individuals):
    """
    Returns a list of (amount, expense) tuples for the given person,
    where each 'All' expense is split equally among all individuals.
    """
    n = len(individuals) if individuals else 1
    result = []
    for e in expenses:
        if 'All' in e.get('people', []):
            share = e['amount'] / n if n > 0 else 0
            if person != 'All':
                if n > 0:
                    result.append((share, e))
            else:
                # For 'All', count the full expense only once
                result.append((e['amount'], e))
        elif person == 'All':
            result.append((e['amount'], e))
        elif person in e.get('people', []):
            result.append((e['amount'], e))
    return result

@app.route('/analytics')
def analytics():
    """
    Analytics tab:
    - Bar chart: income & expense per month for selected year/person
    - Pie chart: category breakdown for selected month/year/person
    - Filters: year, month, person (from subtabs)
    """
    from calendar import month_name
    # Always reload expenses from file to ensure latest data
    expenses = load_json(EXPENSES_FILE, [])
    # Get filters from query params
    selected_person = request.args.get('person', 'All')
    selected_year = int(request.args.get('year', datetime.today().year))
    selected_month = request.args.get('month', 'All')
    pie_mode = request.args.get('pie_mode', 'month')  # 'month' or 'year'

    # --- Bar chart data: Income & Expense per month ---
    months = [f"{selected_year}-{str(m).zfill(2)}" for m in range(1, 13)]
    month_labels = [month_name[m] for m in range(1, 13)]
    incomes_by_month = []
    expenses_by_month = []
    for ym in months:
        # Income for this month/person
        month_budgets = budgets.get(ym, [])
        if selected_person == 'All':
            income = sum(b['income'] for b in month_budgets)
        else:
            income = sum(b['income'] for b in month_budgets if selected_person in b['people'])
        incomes_by_month.append(income)
        # Expenses for this month/person (use split logic)
        if selected_person == 'All':
            filtered_expenses = [e for e in expenses if e['date'][:7] == ym]
            split_mode = False  # No splitting for 'All'
        else:
            # Get (amount, expense) tuples for the selected person, using only filtered expenses
            filtered_expenses = [(amount, e) for amount, e in get_person_expenses(selected_person, [e for e in expenses if e['date'][:7] == ym], individuals)]
            split_mode = True  # Enable splitting for individuals
        # Now filtered_expenses contains the correct split for the selected view.
        if split_mode:
            exp = sum(amount for amount, e in filtered_expenses)
        else:
            exp = sum(e['amount'] for e in filtered_expenses)
        expenses_by_month.append(exp)

    # --- Pie chart data: Category breakdown ---
    pie_data = {}
    # --- Updated Pie Chart Logic for Individual Views ---
    # Use get_person_expenses to split 'All' expenses for individuals
    if pie_mode == 'month' and selected_month != 'All':
        # Pie for selected month
        if selected_person == 'All':
            filtered = [e for e in expenses if e['date'][:7] == selected_month]
            for cat in CATEGORIES:
                pie_data[cat] = sum(e['amount'] for e in filtered if e['category'] == cat)
        else:
            # Filter to selected month and category, then use get_person_expenses
            filtered = [e for e in expenses if e['date'][:7] == selected_month]
            for cat in CATEGORIES:
                # Only include expenses of this category
                cat_expenses = [e for e in filtered if e['category'] == cat]
                pie_data[cat] = sum(amount for amount, e in get_person_expenses(selected_person, cat_expenses, individuals))
    else:
        # Pie for whole year
        if selected_person == 'All':
            filtered = [e for e in expenses if e['date'][:4] == str(selected_year)]
            for cat in CATEGORIES:
                pie_data[cat] = sum(e['amount'] for e in filtered if e['category'] == cat)
        else:
            filtered = [e for e in expenses if e['date'][:4] == str(selected_year)]
            for cat in CATEGORIES:
                cat_expenses = [e for e in filtered if e['category'] == cat]
                pie_data[cat] = sum(amount for amount, e in get_person_expenses(selected_person, cat_expenses, individuals))
    # Remove zero categories
    pie_data = {k: v for k, v in pie_data.items() if v > 0}

    # List of years present in data
    years = sorted(set([int(e['date'][:4]) for e in expenses] + [datetime.today().year]))
    # List of months present in selected year
    months_in_year = sorted(set([e['date'][:7] for e in expenses if e['date'][:4] == str(selected_year)] + months))

    filtered_expenses = filtered
    
    return render_template(
        'analytics.html',
        individuals=individuals,
        selected_person=selected_person,
        years=years,
        selected_year=selected_year,
        months=months,
        month_labels=month_labels,
        selected_month=selected_month,
        incomes_by_month=incomes_by_month,
        expenses_by_month=expenses_by_month,
        pie_data=pie_data,
        pie_labels=list(pie_data.keys()),
        pie_values=list(pie_data.values()),
        pie_mode=pie_mode,
        months_in_year=months_in_year
    )

# --- Sample Data Loader for Development/Learning ---
@app.route('/load_sample_data')
def load_sample_data():
    """
    Fills the app with realistic dummy data for 3 months (quarter):
    - 2 individuals (Ronit, Pallavi)
    - Expenses, budgets, and goals for Feb, Mar, Apr 2025
    - Overwrites any existing in-memory data
    """
    global individuals, expenses, budgets, goals
    individuals = ['Ronit', 'Pallavi']
    expenses = []
    budgets = {}
    goals = {}
    # Dates for each month (2025-02, 2025-03, 2025-04)
    months = ['2025-02', '2025-03', '2025-04']
    # Sample budgets/incomes
    for m in months:
        budgets[m] = [
            {'people': ['All'], 'budget': 30000 + 1000 * months.index(m), 'income': 40000 + 2000 * months.index(m)}
        ]
    # Sample goals
    for m in months:
        goals[m] = [
            {'type': 'save', 'amount': 5000 + 500 * months.index(m), 'category': 'Investments', 'desc': f'Save for SIP ({m})', 'people': ['Ronit']},
            {'type': 'spend', 'amount': 8000 + 800 * months.index(m), 'category': 'Shopping', 'desc': f'Limit shopping ({m})', 'people': ['Pallavi']}
        ]
    # Sample expenses (mix of categories, people, dates)
    sample_expenses = [
        # Feb
        {'date': '2025-02-05', 'amount': 2000, 'category': 'Groceries', 'description': 'Big Bazaar', 'people': ['All']},
        {'date': '2025-02-10', 'amount': 1200, 'category': 'Electricity', 'description': 'Feb Bill', 'people': ['Ronit']},
        {'date': '2025-02-15', 'amount': 1500, 'category': 'Shopping', 'description': 'Clothes', 'people': ['Pallavi']},
        # Mar
        {'date': '2025-03-03', 'amount': 2200, 'category': 'Groceries', 'description': 'D-Mart', 'people': ['All']},
        {'date': '2025-03-12', 'amount': 1300, 'category': 'Gas', 'description': 'Gas Refill', 'people': ['Ronit']},
        {'date': '2025-03-18', 'amount': 1800, 'category': 'Eating Out', 'description': 'Family Dinner', 'people': ['All']},
        # Apr
        {'date': '2025-04-02', 'amount': 2100, 'category': 'Groceries', 'description': 'Reliance Fresh', 'people': ['All']},
        {'date': '2025-04-11', 'amount': 1250, 'category': 'Internet', 'description': 'WiFi', 'people': ['Pallavi']},
        {'date': '2025-04-20', 'amount': 1700, 'category': 'Shopping', 'description': 'Shoes', 'people': ['Ronit']},
    ]
    expenses.extend(sample_expenses)
    return redirect(url_for('home'))


# --- Delete Expense Route (needed for template) ---
@app.route('/api/edit_expense/<expense_id>', methods=['POST'])
def api_edit_expense(expense_id):
    from flask import jsonify, request
    # Always reload the expenses from the file to ensure the latest data
    expenses = load_json(EXPENSES_FILE, [])
    for exp in expenses:
        if exp['id'] == expense_id:
            data = request.get_json()
            exp['date'] = data.get('date', exp['date'])
            exp['amount'] = float(data.get('amount', exp['amount']))
            exp['category'] = data.get('category', exp['category'])
            exp['investment_subcategory'] = data.get('investment_subcategory', exp.get('investment_subcategory', ''))
            exp['people'] = data.get('people', exp['people'])
            exp['description'] = data.get('description', exp.get('description', ''))
            save_json(EXPENSES_FILE, expenses)
            return jsonify({'status': 'success', 'expense': exp})
    return jsonify({'status': 'error', 'message': 'Expense not found'}), 404

@app.route('/delete_budget/<month>/<int:index>', methods=['POST'])
def delete_budget(month, index):
    """
    Deletes a budget entry for the given month and index.
    Matches the template's url_for('delete_budget', month=..., index=...)
    """
    global budgets
    if month in budgets and 0 <= index < len(budgets[month]):
        del budgets[month][index]
        # Clean up empty lists to avoid clutter
        if not budgets[month]:
            del budgets[month]
    return redirect(url_for('home'))

# --- Edit Budget Route (needed for template) ---
@app.route('/edit_budget/<month>/<int:index>', methods=['POST'])
def edit_budget(month, index):
    """
    Edits a budget entry for the given month and index.
    Updates the entry with form data.
    Matches the template's url_for('edit_budget', month=..., index=...)
    """
    global budgets
    if month in budgets and 0 <= index < len(budgets[month]):
        # Get updated data from form
        people = request.form.getlist('people')
        budget_amt = float(request.form.get('budget', 0))
        income_amt = float(request.form.get('income', 0))
        budgets[month][index] = {
            'people': people,
            'budget': budget_amt,
            'income': income_amt
        }
    return redirect(url_for('home'))

# In-memory storage for goals by month (e.g., {'2025-04': [goal1, goal2, ...]})
# Each goal is a dict: {'type': 'save'/'spend', 'amount': float, 'category': str or '', 'desc': str, 'people': list}
goals = {}  # e.g., {'2025-04': [goal1, goal2, ...]}

# List of common Indian expense categories
CATEGORIES = [
    'Groceries', 'Rent', 'Utilities', 'Transport', 'Eating Out', 'Shopping',
    'Health', 'Entertainment', 'Education', 'Investments', 'Gifts', 'Other'
]

@app.route('/', methods=['GET', 'POST'])
def home():
    """
    Handles the home page, including:
    - Displaying the expense entry form
    - Processing form submissions
    - Showing the list of expenses, with filtering, summaries, and budget/income status
    - Handles per-person and collective views
    """
    today = datetime.today().strftime('%Y-%m-%d')
    # --- Handle individual selection (via query param or default) ---
    selected_person = request.args.get('person', 'All')
    show_collective = (selected_person == 'All')
    # --- Handle new expense submission (POST) ---
    if request.method == 'POST':
        # Get data from the submitted form
        date_str = request.form.get('date')
        amount_str = request.form.get('amount')
        category = request.form.get('category')
        description = request.form.get('description', '')
        people = request.form.getlist('people')
        if not people:
            people = ['All']
        # Validate and process form data
        try:
            # Parse date (default to today if not provided)
            if date_str:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                date = datetime.today().date()
            # Parse amount (must be a positive number)
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError('Amount must be positive.')
            for p in people:
                if p != 'All' and p not in individuals:
                    raise ValueError('Invalid person.')
        except Exception as e:
            return render_template(
                'index.html',
                expenses=expenses,
                categories=CATEGORIES,
                individuals=individuals,
                selected_person=selected_person,
                error=str(e),
                today=today
            )
        # Add the new expense to the list
        expenses.append({
            'id': str(uuid.uuid4()),
            'date': date.strftime('%Y-%m-%d'),
            'amount': amount,
            'category': category,
            'description': description,
            'people': people
        })
        # Redirect to avoid form resubmission, keep person tab
        return redirect(url_for('home', person=selected_person))

    # --- Handle filtering (GET) ---
    # Get filter values from query parameters
    filter_category = request.args.get('filter_category', '')
    filter_start = request.args.get('filter_start', '')
    filter_end = request.args.get('filter_end', '')

    # Filter expenses list by people and filters
    if show_collective:
        filtered_expenses = expenses
        split_mode = False
    else:
        # For a specific person, get (amount, expense) tuples for their share (including 'All' splits)
        filtered_expenses = get_person_expenses(selected_person, expenses, individuals)
        split_mode = True
    # Apply filters (category/date) to the correct structure
    if show_collective:
        if filter_category:
            filtered_expenses = [e for e in filtered_expenses if e['category'] == filter_category]
        if filter_start:
            filtered_expenses = [e for e in filtered_expenses if e['date'] >= filter_start]
        if filter_end:
            filtered_expenses = [e for e in filtered_expenses if e['date'] <= filter_end]
    else:
        if filter_category:
            filtered_expenses = [item for item in filtered_expenses if item[1]['category'] == filter_category]
        if filter_start:
            filtered_expenses = [item for item in filtered_expenses if item[1]['date'] >= filter_start]
        if filter_end:
            filtered_expenses = [item for item in filtered_expenses if item[1]['date'] <= filter_end]

    # Calculate total spent for filtered results (use split logic)
    if show_collective:
        total_spent = sum(e['amount'] for e in filtered_expenses)
    else:
        total_spent = sum(amount for amount, _ in filtered_expenses)

    # --- Budget & Income logic for the selected month and person ---
    # Determine the current month (YYYY-MM) based on filter or today
    if filter_start:
        current_month = filter_start[:7]
    else:
        current_month = today[:7]
    # Get budget and income for the month and person (default to 0 if not set)
    # For budgets/incomes: sum all entries tagged to 'All' or selected_person
    def sum_budgets(month):
        return sum(b['budget'] for b in budgets.get(month, []) if 'All' in b['people'] or (not show_collective and selected_person in b['people']))
    def sum_incomes(month):
        return sum(b.get('income', 0) for b in budgets.get(month, []) if 'All' in b['people'] or (not show_collective and selected_person in b['people']))
    month_budget = sum_budgets(current_month)
    month_income = sum_incomes(current_month)
    # Calculate budget left and savings
    budget_left = month_budget - total_spent
    savings = month_income - total_spent
    # Budget status for UI feedback
    if month_budget == 0:
        budget_status = 'no-budget'
    elif total_spent < month_budget * 0.8:
        budget_status = 'under'
    elif total_spent <= month_budget:
        budget_status = 'near'
    else:
        budget_status = 'over'

    # --- Goals logic for the selected month and person ---
    # Get goals for this month and person(s)
    # Goals: show all tagged to 'All' or selected_person
    if current_month in goals:
        if show_collective:
            month_goals_raw = [g for g in goals[current_month] if 'All' in g['people'] or any(p in g['people'] for p in individuals)]
        else:
            month_goals_raw = [g for g in goals[current_month] if 'All' in g['people'] or selected_person in g['people']]
    else:
        month_goals_raw = []
    goals_with_progress = []
    for goal in month_goals_raw:
        # Calculate progress based on goal type
        if goal['type'] == 'save':
            progress = savings / goal['amount'] if goal['amount'] else 0
            achieved = savings >= goal['amount']
        elif goal['type'] == 'spend':
            # Only sum expenses for entries tagged to this goal's people
            def expense_match(e):
                return (goal['category'] == '' or e['category'] == goal['category']) and e['date'].startswith(current_month) and (set(goal['people']) & set(e['people']) or 'All' in e['people'])
            spent = sum(e['amount'] for e in expenses if expense_match(e))
            progress = max(0, 1 - spent / goal['amount']) if goal['amount'] else 0
            achieved = spent <= goal['amount']
        else:
            progress = 0
            achieved = False
        bar_progress = min(max(progress, 0), 1)
        goals_with_progress.append({
            **goal,
            'progress': progress,
            'bar_progress': bar_progress,
            'achieved': achieved
        })

    # --- MoM and YoY comparison logic (per person/collective) ---
    from calendar import monthrange
    def prev_month_str(ym):
        y, m = map(int, ym.split('-'))
        if m == 1:
            return f"{y-1}-12"
        else:
            return f"{y}-{m-1:02d}"
    def last_year_str(ym):
        y, m = map(int, ym.split('-'))
        return f"{y-1}-{m:02d}"
    prev_month = prev_month_str(current_month)
    last_year_month = last_year_str(current_month)
    # Expenses
    def month_sum_expenses(ym):
        if show_collective:
            return sum(e['amount'] for e in expenses if e['date'].startswith(ym))
        else:
            # Use split logic for per-person
            return sum(amount for amount, e in get_person_expenses(selected_person, [e for e in expenses if e['date'].startswith(ym)], individuals))
    curr_exp = month_sum_expenses(current_month)
    prev_exp = month_sum_expenses(prev_month)
    last_year_exp = month_sum_expenses(last_year_month)
    # Incomes
    def month_income(ym):
        return sum_incomes(ym)
    curr_inc = month_income(current_month)
    prev_inc = month_income(prev_month)
    last_year_inc = month_income(last_year_month)
    # Percent change helper
    def pct_change(curr, prev):
        if prev == 0:
            return None if curr == 0 else float('inf')
        return ((curr - prev) / prev) * 100
    mom_exp = pct_change(curr_exp, prev_exp)
    yoy_exp = pct_change(curr_exp, last_year_exp)
    mom_inc = pct_change(curr_inc, prev_inc)
    yoy_inc = pct_change(curr_inc, last_year_inc)

    # Render the page with all info
    # Always provide budgets, goals, and month_goals to template (never undefined)
    
    return render_template(
        'index.html',
        expenses=filtered_expenses,
        categories=CATEGORIES,
        individuals=individuals,
        selected_person=selected_person,
        error=None,
        today=today,
        filter_category=filter_category,
        filter_start=filter_start,
        filter_end=filter_end,
        total_spent=total_spent,
        month_budget=month_budget,
        month_income=month_income,
        budget_left=budget_left,
        savings=savings,
        budget_status=budget_status,
        current_month=current_month,
        budgets=budgets if budgets is not None else {},
        goals=goals if goals is not None else {},
        month_goals=goals_with_progress if 'goals_with_progress' in locals() else [],
        show_collective=show_collective,
        # MoM/YoY context
        curr_exp=curr_exp, prev_exp=prev_exp, last_year_exp=last_year_exp,
        curr_inc=curr_inc, prev_inc=prev_inc, last_year_inc=last_year_inc,
        mom_exp=mom_exp, yoy_exp=yoy_exp, mom_inc=mom_inc, yoy_inc=yoy_inc
    )

@app.route('/delete/<expense_id>', methods=['POST'])
def delete_expense(expense_id):
    """
    Delete an expense by its unique ID in the expenses list.
    Redirects back to the home page after deletion.
    """
    global expenses
    try:
        expense_idx = next((i for i, e in enumerate(expenses) if e.get('id') == expense_id), None)
        if expense_idx is not None:
            del expenses[expense_idx]
            save_json(EXPENSES_FILE, expenses)
    except Exception as e:
        logging.error(f"Failed to delete expense: {e}")
    return redirect(url_for('home'))

@app.route('/edit/<expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    """
    Edit an expense by its unique ID.
    Edit an expense by its index.
    - GET: Show the home page with the form pre-filled for editing.
    - POST: Update the expense and redirect to home.
    """
    global expenses
    from datetime import datetime
    today = datetime.today().strftime('%Y-%m-%d')
    # Find the expense by ID
    expense_idx = next((i for i, e in enumerate(expenses) if e.get('id') == expense_id), None)
    if expense_idx is None:
        return "Expense not found", 404
    if request.method == 'POST':
        # Get updated data from form
        date_str = request.form.get('date')
        amount_str = request.form.get('amount')
        category = request.form.get('category')
        description = request.form.get('description', '')
        try:
            if date_str:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                date = datetime.today().date()
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError('Amount must be positive.')
        except Exception as e:
            # Replicate filtering and summary logic from home route for robust context
            selected_person = request.args.get('person', 'All')
            show_collective = (selected_person == 'All')
            filter_category = request.args.get('filter_category', '')
            filter_start = request.args.get('filter_start', '')
            filter_end = request.args.get('filter_end', '')
            if show_collective:
                filtered_expenses = expenses
            else:
                filtered_expenses = [e for e in expenses if 'All' in e['people'] or selected_person in e['people']]
            if filter_category:
                filtered_expenses = [e for e in filtered_expenses if e['category'] == filter_category]
            if filter_start:
                filtered_expenses = [e for e in filtered_expenses if e['date'] >= filter_start]
            if filter_end:
                filtered_expenses = [e for e in filtered_expenses if e['date'] <= filter_end]
            total_spent = sum(e['amount'] for e in filtered_expenses)
            if filter_start:
                current_month = filter_start[:7]
            else:
                current_month = today[:7]
            def sum_budgets(month):
                return sum(b['budget'] for b in budgets.get(month, []) if 'All' in b['people'] or (not show_collective and selected_person in b['people']))
            def sum_incomes(month):
                return sum(b.get('income', 0) for b in budgets.get(month, []) if 'All' in b['people'] or (not show_collective and selected_person in b['people']))
            month_budget = sum_budgets(current_month)
            month_income = sum_incomes(current_month)
            budget_left = month_budget - total_spent
            savings = month_income - total_spent
            if month_budget == 0:
                budget_status = 'no-budget'
            elif total_spent < month_budget * 0.8:
                budget_status = 'under'
            elif total_spent <= month_budget:
                budget_status = 'near'
            else:
                budget_status = 'over'
            from calendar import monthrange
            def prev_month_str(ym):
                y, m = map(int, ym.split('-'))
                if m == 1:
                    return f"{y-1}-12"
                else:
                    return f"{y}-{m-1:02d}"
            def last_year_str(ym):
                y, m = map(int, ym.split('-'))
                return f"{y-1}-{m:02d}"
            prev_month = prev_month_str(current_month)
            last_year_month = last_year_str(current_month)
            def month_sum_expenses(ym):
                if show_collective:
                    return sum(e['amount'] for e in expenses if e['date'].startswith(ym))
                else:
                    return sum(e['amount'] for e in expenses if ('All' in e['people'] or selected_person in e['people']) and e['date'].startswith(ym))
            curr_exp = month_sum_expenses(current_month)
            prev_exp = month_sum_expenses(prev_month)
            last_year_exp = month_sum_expenses(last_year_month)
            def month_income(ym):
                return sum_incomes(ym)
            curr_inc = month_income(current_month)
            prev_inc = month_income(prev_month)
            last_year_inc = month_income(last_year_month)
            def pct_change(curr, prev):
                if prev == 0:
                    return None if curr == 0 else float('inf')
                return ((curr - prev) / prev) * 100
            mom_exp = pct_change(curr_exp, prev_exp)
            yoy_exp = pct_change(curr_exp, last_year_exp)
            mom_inc = pct_change(curr_inc, prev_inc)
            yoy_inc = pct_change(curr_inc, last_year_inc)
            # Goals logic (optional, for completeness)
            if current_month in goals:
                if show_collective:
                    month_goals_raw = [g for g in goals[current_month] if 'All' in g['people'] or any(p in g['people'] for p in individuals)]
                else:
                    month_goals_raw = [g for g in goals[current_month] if 'All' in g['people'] or selected_person in g['people']]
            else:
                month_goals_raw = []
            goals_with_progress = []
            for goal in month_goals_raw:
                if goal['type'] == 'save':
                    progress = savings / goal['amount'] if goal['amount'] else 0
                    achieved = savings >= goal['amount']
                elif goal['type'] == 'spend':
                    def expense_match(e):
                        return (goal['category'] == '' or e['category'] == goal['category']) and e['date'].startswith(current_month) and (set(goal['people']) & set(e['people']) or 'All' in e['people'])
                    spent = sum(e['amount'] for e in expenses if expense_match(e))
                    progress = max(0, 1 - spent / goal['amount']) if goal['amount'] else 0
                    achieved = spent <= goal['amount']
                else:
                    progress = 0
                    achieved = False
                bar_progress = min(max(progress, 0), 1)
                goals_with_progress.append({
                    **goal,
                    'progress': progress,
                    'bar_progress': bar_progress,
                    'achieved': achieved
                })
            return render_template(
                'index.html',
                expenses=filtered_expenses,
                categories=CATEGORIES,
                individuals=individuals,
                selected_person=selected_person,
                error=str(e),
                today=today,
                edit_index=index,
                edit_expense={
                    'date': date_str,
                    'amount': amount_str,
                    'category': category,
                    'description': description
                },
                filter_category=filter_category,
                filter_start=filter_start,
                filter_end=filter_end,
                total_spent=total_spent,
                month_budget=month_budget,
                month_income=month_income,
                budget_left=budget_left,
                savings=savings,
                budget_status=budget_status,
                current_month=current_month,
                budgets=budgets if budgets is not None else {},
                goals=goals if goals is not None else {},
                month_goals=goals_with_progress if 'goals_with_progress' in locals() else [],
                show_collective=show_collective,
                curr_exp=curr_exp, prev_exp=prev_exp, last_year_exp=last_year_exp,
                curr_inc=curr_inc, prev_inc=prev_inc, last_year_inc=last_year_inc,
                mom_exp=mom_exp, yoy_exp=yoy_exp, mom_inc=mom_inc, yoy_inc=yoy_inc
            )
        # Update the expense
        expenses[expense_idx] = {
            **expenses[expense_idx],  # retain id and any other fields
            'date': date.strftime('%Y-%m-%d'),
            'amount': amount,
            'category': category,
            'description': description
        }
        save_json(EXPENSES_FILE, expenses)  # Save after editing
        return redirect(url_for('home'))
    # GET: Render form pre-filled for editing
    # Replicate context from home route for robust template rendering
    selected_person = request.args.get('person', 'All')
    show_collective = (selected_person == 'All')
    filter_category = request.args.get('filter_category', '')
    filter_start = request.args.get('filter_start', '')
    filter_end = request.args.get('filter_end', '')
    if show_collective:
        filtered_expenses = expenses
    else:
        filtered_expenses = [e for e in expenses if 'All' in e['people'] or selected_person in e['people']]
    if filter_category:
        filtered_expenses = [e for e in filtered_expenses if e['category'] == filter_category]
    if filter_start:
        filtered_expenses = [e for e in filtered_expenses if e['date'] >= filter_start]
    if filter_end:
        filtered_expenses = [e for e in filtered_expenses if e['date'] <= filter_end]
    total_spent = sum(e['amount'] for e in filtered_expenses)
    if filter_start:
        current_month = filter_start[:7]
    else:
        current_month = today[:7]
    def sum_budgets(month):
        return sum(b['budget'] for b in budgets.get(month, []) if 'All' in b['people'] or (not show_collective and selected_person in b['people']))
    def sum_incomes(month):
        return sum(b.get('income', 0) for b in budgets.get(month, []) if 'All' in b['people'] or (not show_collective and selected_person in b['people']))
    month_budget = sum_budgets(current_month)
    month_income = sum_incomes(current_month)
    budget_left = month_budget - total_spent
    savings = month_income - total_spent
    if month_budget == 0:
        budget_status = 'no-budget'
    elif total_spent < month_budget * 0.8:
        budget_status = 'under'
    elif total_spent <= month_budget:
        budget_status = 'near'
    else:
        budget_status = 'over'
    # Goals logic
    if current_month in goals:
        if show_collective:
            month_goals_raw = [g for g in goals[current_month] if 'All' in g['people'] or any(p in g['people'] for p in individuals)]
        else:
            month_goals_raw = [g for g in goals[current_month] if 'All' in g['people'] or selected_person in g['people']]
    else:
        month_goals_raw = []
    goals_with_progress = []
    for goal in month_goals_raw:
        if goal['type'] == 'save':
            progress = savings / goal['amount'] if goal['amount'] else 0
            achieved = savings >= goal['amount']
        elif goal['type'] == 'spend':
            def expense_match(e):
                return (goal['category'] == '' or e['category'] == goal['category']) and e['date'].startswith(current_month) and (set(goal['people']) & set(e['people']) or 'All' in e['people'])
            spent = sum(e['amount'] for e in expenses if expense_match(e))
            progress = max(0, 1 - spent / goal['amount']) if goal['amount'] else 0
            achieved = spent <= goal['amount']
        else:
            progress = 0
            achieved = False
        bar_progress = min(max(progress, 0), 1)
        goals_with_progress.append({
            **goal,
            'progress': progress,
            'bar_progress': bar_progress,
            'achieved': achieved
        })
    from calendar import monthrange
    def prev_month_str(ym):
        y, m = map(int, ym.split('-'))
        if m == 1:
            return f"{y-1}-12"
        else:
            return f"{y}-{m-1:02d}"
    def last_year_str(ym):
        y, m = map(int, ym.split('-'))
        return f"{y-1}-{m:02d}"
    prev_month = prev_month_str(current_month)
    last_year_month = last_year_str(current_month)
    def month_sum_expenses(ym):
        if show_collective:
            return sum(e['amount'] for e in expenses if e['date'].startswith(ym))
        else:
            return sum(e['amount'] for e in expenses if ('All' in e['people'] or selected_person in e['people']) and e['date'].startswith(ym))
    curr_exp = month_sum_expenses(current_month)
    prev_exp = month_sum_expenses(prev_month)
    last_year_exp = month_sum_expenses(last_year_month)
    def month_income(ym):
        return sum_incomes(ym)
    curr_inc = month_income(current_month)
    prev_inc = month_income(prev_month)
    last_year_inc = month_income(last_year_month)
    def pct_change(curr, prev):
        if prev == 0:
            return None if curr == 0 else float('inf')
        return ((curr - prev) / prev) * 100
    mom_exp = pct_change(curr_exp, prev_exp)
    yoy_exp = pct_change(curr_exp, last_year_exp)
    mom_inc = pct_change(curr_inc, prev_inc)
    yoy_inc = pct_change(curr_inc, last_year_inc)
    
    return render_template(
        'index.html',
        expenses=filtered_expenses,
        categories=CATEGORIES,
        individuals=individuals,
        selected_person=selected_person,
        error=None,
        today=today,
        edit_index=expense_idx,
        edit_expense=expenses[expense_idx],
        filter_category=filter_category,
        filter_start=filter_start,
        filter_end=filter_end,
        total_spent=total_spent,
        month_budget=month_budget,
        month_income=month_income,
        budget_left=budget_left,
        savings=savings,
        budget_status=budget_status,
        current_month=current_month,
        budgets=budgets if budgets is not None else {},
        goals=goals if goals is not None else {},
        month_goals=goals_with_progress if 'goals_with_progress' in locals() else [],
        show_collective=show_collective,
        curr_exp=curr_exp, prev_exp=prev_exp, last_year_exp=last_year_exp,
        curr_inc=curr_inc, prev_inc=prev_inc, last_year_inc=last_year_inc,
        mom_exp=mom_exp, yoy_exp=yoy_exp, mom_inc=mom_inc, yoy_inc=yoy_inc
    )

@app.route('/set_budget_income', methods=['POST'])
def set_budget_income():
    """
    Set the monthly budget and income for the selected month and people (multi-tag).
    """
    global budgets
    month = request.form.get('month')  # format: YYYY-MM
    budget = request.form.get('budget')
    income = request.form.get('income')
    people = request.form.getlist('people')
    if not people:
        people = ['All']
    try:
        budget = float(budget) if budget else 0
        income = float(income) if income else 0
    except ValueError:
        budget = 0
        income = 0
    if month:
        budgets.setdefault(month, []).append({'people': people, 'budget': budget, 'income': income})
    save_json(BUDGETS_FILE, budgets)  # Save budgets after update
    return redirect(url_for('home', filter_start=month+'-01' if month else '', person=people[0] if people and people[0] != 'All' else 'All'))

@app.route('/individuals', methods=['GET', 'POST'])
def manage_individuals():
    """
    View and edit the list of individuals (names).
    """
    global individuals
    if request.method == 'POST':
        # Get the submitted names (comma separated or list)
        names = request.form.getlist('individuals')
        # Clean up and filter empty names
        new_names = [n.strip() for n in names if n.strip()]
        if new_names:
            individuals = new_names
    save_json(INDIVIDUALS_FILE, individuals)  # Save individuals after update
    return redirect(url_for('home'))

@app.route('/expenses', methods=['GET', 'POST'])
def expenses_tab():
    print("DEBUG: expenses_tab route called")
    """
    Expenses tab: Filter, add, edit, and delete expenses.
    - Default filter: current month/year and All person
    - Add/Edit/Delete with confirmation
    """
    from calendar import month_name
    # Always reload expenses from file to ensure latest data
    expenses = load_json(EXPENSES_FILE, [])
    split_mode = False  # Always define split_mode for template
    # Default filters
    today = datetime.today()
    default_month = f"{today.year}-{str(today.month).zfill(2)}"
    selected_person = request.args.get('person', 'All')
    selected_months = request.args.getlist('month')
    selected_categories = request.args.getlist('category')
    # Get raw lists (may contain empty string if hidden input submitted)
    selected_months_raw = request.args.getlist('month')
    selected_categories_raw = request.args.getlist('category')
    # Normalize: treat [] and [''] as empty
    selected_months = [m for m in selected_months_raw if m]
    selected_categories = [c for c in selected_categories_raw if c]

    # List of months for dropdown (all months present in expenses + current month)
    months = sorted(set([exp['date'][:7] for exp in expenses] + [default_month]))
    categories = CATEGORIES

    # Detect if user actually submitted the filter (parameter present)
    month_param_present = 'month' in request.args
    category_param_present = 'category' in request.args

    # If param present and list is empty (including ['']), filter to none
    months_to_filter = selected_months if (month_param_present and selected_months) else (["__NONE__"] if month_param_present else [m for m in months])
    cats_to_filter = selected_categories if (category_param_present and selected_categories) else (["__NONE__"] if category_param_present else [c for c in categories])

    # For UI: if param present, always pass selected (could be []), else pass all
    selected_months_ui = selected_months if month_param_present else [m for m in months]
    selected_categories_ui = selected_categories if category_param_present else [c for c in categories]

    # Filtering logic
    def filter_exp(e):
        # Person filter
        if selected_person != 'All' and selected_person not in e.get('people', []):
            return False
        # Month filter
        if e['date'][:7] not in months_to_filter:
            return False
        # Category filter
        if e['category'] not in cats_to_filter:
            return False
        return True

    # Filter expenses
    filtered_expenses = [e for e in expenses if filter_exp(e)]

    # Handle POST: add new expense
    if request.method == 'POST' and request.form.get('action') == 'add':
        # After adding, redirect will re-enter the function, so split_mode will be set appropriately on GET
        pass
        # Gather form data
        date = request.form.get('date', today.strftime('%Y-%m-%d'))
        amount = float(request.form.get('amount', 0))
        category = request.form.get('category', '')
        description = request.form.get('description', '')
        people = request.form.getlist('people') or ['All']
        investment_subcategory = request.form.get('investment_subcategory', '').strip()

        # If category is Investments, require subcategory and only allow a single person (not 'All')
        if category == 'Investments':
            if not investment_subcategory:
                # Return with error (for now, just redirect back; ideally show error)
                return redirect(url_for('expenses_tab', person=selected_person, month=selected_month, category=selected_category))
            # Disallow 'All' or multiple people for investments
            if 'All' in people or len(people) != 1:
                # Return with error (for now, just redirect back; ideally show error)
                return redirect(url_for('expenses_tab', person=selected_person, month=selected_month, category=selected_category))
            person = people[0]
            investments.setdefault(person, {})
            investments[person][investment_subcategory] = investments[person].get(investment_subcategory, 0) + amount
        else:
            investment_subcategory = ''  # Not relevant

        # Add new expense (store subcategory for record)
        import uuid
        expenses.append({
            'id': str(uuid.uuid4()),
            'date': date,
            'amount': amount,
            'category': category,
            'description': description,
            'people': people,
            'investment_subcategory': investment_subcategory
        })
        save_json(EXPENSES_FILE, expenses)  # Save after adding expense
        # AJAX support
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask import jsonify
            return jsonify({'status': 'success', 'message': 'Expense saved.'})
        return redirect(url_for('expenses_tab', person=selected_person, month=selected_month, category=selected_category))
    # ... (rest of the code remains the same)
    # Filtering logic for GET and after POST redirect
    if selected_person == 'All':
        filtered_expenses = [e for e in expenses if filter_exp(e)]
        split_mode = False
    else:
        filtered_expenses = [(amount, e) for amount, e in get_person_expenses(selected_person, [e for e in expenses if filter_exp(e)], individuals)]
        split_mode = True

    
    
    

    # Prepare investment categories for the subcategory dropdown
    investment_categories = [cat for cat, _ in INVESTMENT_CATEGORIES]
    return render_template(
        'expenses.html',
        individuals=individuals,
        selected_person=selected_person,
        months=months,
        selected_months=selected_months_ui,
        categories=categories,
        selected_categories=selected_categories_ui,
        expenses=filtered_expenses,
        split_mode=split_mode,  # Pass flag to template
        today=today.strftime('%Y-%m-%d'),
        investment_categories=investment_categories
    )

# --- Asset categories and icons for investments ---
INVESTMENT_CATEGORIES = [
    ('Mutual Funds', 'bi-piggy-bank'),
    ('Indian Stocks', 'bi-bar-chart'),
    ('Indian Unlisted Stocks', 'bi-building'),
    ('International Stocks', 'bi-globe'),
    ('International Unlisted Stocks', 'bi-globe2'),
    ('EPF', 'bi-bank'),
    ('ULIPs', 'bi-shield-lock'),
    ('Gold', 'bi-gem'),
    ('Crypto', 'bi-currency-bitcoin'),
    ('Indian Bonds', 'bi-cash-coin'),
    ('International Bonds', 'bi-cash-stack'),
    ('Real Estate', 'bi-house-door'),
]

# In-memory investments: investments[person][category] = amount
if 'investments' not in globals():
    investments = {}

@app.route('/investments', methods=['GET'])
def investments_tab():
    """
    Investments tab: Show investments by category/person, derived from expenses only.
    """
    # Always reload expenses from file to ensure latest data
    expenses = load_json(EXPENSES_FILE, [])
    selected_person = request.args.get('person', 'All')
    # Build a map: investments[person][subcategory] = sum of expenses
    investments_calc = {p: {cat: 0 for cat, _ in INVESTMENT_CATEGORIES} for p in individuals}
    for e in expenses:
        if e.get('category') == 'Investments':
            subcat = e.get('investment_subcategory', 'Other')
            for p in e.get('people', []):
                if p in investments_calc and subcat in investments_calc[p]:
                    investments_calc[p][subcat] += e.get('amount', 0)
    # Prepare investment data for this person or All
    person_investments = {}
    if selected_person == 'All':
        for cat, _ in INVESTMENT_CATEGORIES:
            person_investments[cat] = sum(
                investments_calc.get(p, {}).get(cat, 0) for p in individuals
            )
    else:
        for cat, _ in INVESTMENT_CATEGORIES:
            person_investments[cat] = investments_calc.get(selected_person, {}).get(cat, 0)
    # Sort categories by amount descending
    sorted_cats = sorted(INVESTMENT_CATEGORIES, key=lambda x: -person_investments[x[0]])
    return render_template(
        'investments.html',
        individuals=individuals,
        selected_person=selected_person,
        investment_data=[
            {
                'category': cat,
                'icon': icon,
                'amount': person_investments[cat]
            } for cat, icon in sorted_cats
        ],
        categories=[cat for cat, _ in INVESTMENT_CATEGORIES]
    )

@app.route('/income_tab')
def income_tab():
    """
    Renders the income tab page with correct data.
    """
    from calendar import month_name
    selected_person = request.args.get('person', 'All')
    all_years = sorted({int(k.split('-')[0]) for k in budgets.keys()})
    if not all_years:
        all_years = [datetime.today().year]
    selected_year = int(request.args.get('year', datetime.today().year))
    if selected_year not in all_years:
        selected_year = all_years[-1]
    months = [(f"{selected_year}-{str(m).zfill(2)}", month_name[m]) for m in range(1, 13)]
    income_entries = []
    if selected_person == 'All':
        for ym, mn in months:
            total_income = 0
            for person in individuals:
                entry = next((b for b in budgets.get(ym, []) if person in b['people']), None)
                if entry:
                    total_income += entry['income']
            income_entries.append({'month': mn, 'income': total_income, 'ym': ym})
        can_edit = False
    else:
        for ym, mn in months:
            entry = next((b for b in budgets.get(ym, []) if selected_person in b['people']), None)
            income = entry['income'] if entry else 0
            income_entries.append({'month': mn, 'income': income, 'ym': ym})
        can_edit = True
    return render_template(
        'income.html',
        individuals=individuals,
        selected_person=selected_person,
        months=months,
        income_entries=income_entries,
        years=all_years,
        selected_year=selected_year,
        can_edit=can_edit
    )

# Route for the homepage
@app.route('/')
def index():
    """Show the main dashboard page."""
    return render_template('index.html')

# Error handler for uncaught exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception("Unhandled Exception: %s", e)
    return render_template("error.html", error=e), 500

if __name__ == '__main__':
    # Run the app in debug mode for easy testing
    app.run(debug=True)
