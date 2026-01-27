from datetime import datetime, timedelta

import pytz
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from models import Task, User, db
from sqlalchemy import or_

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://db_user:db_password@localhost/app_db"  # 接続先DBを定義
app.secret_key = "deadbeef"
db.init_app(app)
Migrate(app, db)

login_manager = LoginManager()
login_manager.login_view = "login"  # ログインせずログインが必要な画面にアクセスした場合 /login に移動
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        # GETリクエスト時は空のフォームを表示
        return render_template("register.html", title="ユーザ登録")

    # POSTメソッドのときの処理
    form_data = request.form

    # 1. 必須項目チェック
    if (
        form_data.get("id") == ""
        or form_data.get("password") == ""
        # 確認用パスワードも必須項目としてチェック
        or form_data.get("confirm_password") == ""
        or form_data.get("lastname") == ""
        or form_data.get("firstname") == ""
    ):
        flash("入力されていない項目があります")
        # 以前の入力を保持して画面に戻る
        return render_template(
            "register.html",
            title="ユーザ登録",
            id=form_data.get("id", ""),
            lastname=form_data.get("lastname", ""),
            firstname=form_data.get("firstname", ""),
        )

    # 2. パスワード一致チェック
    password = form_data.get("password")
    confirm_password = form_data.get("confirm_password")

    if password != confirm_password:
        flash("パスワードと確認用パスワードが一致しません")

        # 登録処理を停止し、エラーフラグと入力値を保持して画面に戻る
        return render_template(
            "register.html",
            title="ユーザ登録",
            id=form_data.get("id", ""),
            lastname=form_data.get("lastname", ""),
            firstname=form_data.get("firstname", ""),
            # フロントエンドで赤枠表示に使用するフラグ
            is_password_mismatch=True,
        )

    # 3. ユーザID重複チェック
    if User.query.get(form_data.get("id")) is not None:
        flash("ユーザを登録できません (このIDは既に使われています)")

        # 以前の入力を保持して画面に戻る
        return render_template(
            "register.html",
            title="ユーザ登録",
            id=form_data.get("id", ""),
            lastname=form_data.get("lastname", ""),
            firstname=form_data.get("firstname", ""),
        )

    # 4. 登録処理
    user = User(
        id=form_data["id"],
        password=form_data["password"],  # モデルのsetterでハッシュ化される
        lastname=form_data["lastname"],
        firstname=form_data["firstname"],
    )
    db.session.add(user)
    db.session.commit()

    # 登録成功後はログイン画面 (またはトップページ) にリダイレクト
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:  # ログイン済ならタスク一覧に移動
        return redirect("/")

    if request.method == "GET":  # GETメソッドならログイン画面を表示
        return render_template("login.html", title="ログイン")
    # POSTメソッドならログイン処理
    user = User.query.get(request.form["id"])
    # 入力されたIDのユーザが存在し，パスワードも正しければタスク一覧に移動
    if user is not None and user.verify_password(request.form["password"]):
        login_user(user)
        return redirect("/")
    # ログインに失敗したらログイン画面に戻る
    flash("ユーザIDかパスワードが誤っています")
    return redirect("/login")


@app.route("/logout")
def logout():  # ログアウトしてログイン画面に戻る
    logout_user()
    return redirect("/login")


@app.route("/")
@login_required
def index():
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst).replace(tzinfo=None)

    # .order_by(Task.deadline) を追加して締切日時の昇順（近い順）に並び替え
    my_tasks = Task.query.filter_by(user=current_user).order_by(Task.deadline).all()

    sort = request.args.get("sort", "deadline")
    order = request.args.get("order", "asc")

    if sort == "id":
        sort_column = Task.id
    elif sort == "name":
        sort_column = Task.name
    elif sort == "deadline":
        sort_column = Task.deadline
    else:
        sort_column = Task.id

    if order == "desc":
        sort_column = sort_column.desc()

    my_tasks = Task.query.filter_by(user=current_user).order_by(sort_column).all()
    shared_tasks = (
        Task.query.filter(
            Task.user_id.in_([f.id for f in list(current_user.followees) + [current_user]]),
            Task.is_shared == True,
        )
        .order_by(sort_column)
        .all()
    )
    tracked_tasks = (
        Task.query.filter(
            Task.user_id == current_user.id,
            Task.is_tracked == True,
        )
        .order_by(sort_column)
        .all()
    )

    for task in my_tasks + shared_tasks + tracked_tasks:
        if task.deadline:
            if task.deadline < now:
                task.is_overdue = True
            elif task.deadline <= now + timedelta(days=7):
                task.is_due_soon = True

    return render_template(
        "index.html",
        title="ホーム",
        my_tasks=my_tasks,
        shared_tasks=shared_tasks,
        tracked_tasks=tracked_tasks,
        now=now,
        timedelta=timedelta,
        sort=sort,
        order=order,  # ← これを渡す
    )


@app.route("/full")
@login_required
def full():
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst).replace(tzinfo=None)

    sort = request.args.get("sort", "deadline")
    order = request.args.get("order", "asc")

    if sort == "id":
        sort_column = Task.id
    elif sort == "name":
        sort_column = Task.name
    elif sort == "deadline":
        sort_column = Task.deadline
    else:
        sort_column = Task.id

    if order == "desc":
        sort_column = sort_column.desc()

    my_tasks = Task.query.filter_by(user=current_user).order_by(sort_column).all()

    shared_tasks = (
        Task.query.filter(
            Task.user_id.in_([f.id for f in list(current_user.followees) + [current_user]]),
            Task.is_shared == True,
        )
        .order_by(sort_column)
        .all()
    )
    tracked_tasks = (
        Task.query.filter(
            Task.user_id == current_user.id,
            Task.is_tracked == True,
        )
        .order_by(sort_column)
        .all()
    )

    for task in my_tasks + shared_tasks + tracked_tasks:
        if task.deadline:
            if task.deadline < now:
                task.is_overdue = True
            elif task.deadline <= now + timedelta(days=7):
                task.is_due_soon = True

    return render_template(
        "full.html",
        title="ホーム",
        my_tasks=my_tasks,
        shared_tasks=shared_tasks,
        now=now,
        timedelta=timedelta,
        tracked_tasks=tracked_tasks,
        sort=sort,
        order=order,
    )  # 2種類のタスクをテンプレートに渡す


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    name = request.form["name"]
    deadline_raw = request.form["deadline"]

    # 入力チェック
    if not name and not deadline_raw:
        flash("タスク名と締切日時が入力されていません")
        return redirect("/")
    elif not name:
        flash("タスク名を入力してください")
        return redirect("/")
    elif not deadline_raw:
        flash("締切日時を入力してください")
        return redirect("/")

    try:
        deadline = datetime.strptime(deadline_raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("締切日時の形式が正しくありません")
        return redirect("/")

    task = Task(
        user=current_user,
        name=request.form["name"],
        deadline=deadline,
        is_shared=request.form.get("is_shared") is not None,  # フォームの内容で共有フラグを更新
        is_tracked=request.form.get("is_tracked") is not None,
    )

    db.session.add(task)  # 用意したタスクを保存
    db.session.commit()  # 保存した状態をDBに反映
    return redirect("/")  # タスク一覧に戻る


@app.route("/completed", methods=["GET", "POST"])
@login_required
def completed():
    sort = request.args.get("sort", "deadline")  # デフォルトは締切日時
    order = request.args.get("order", "asc")  # デフォルトは昇順

    # 並び替え対象を決定
    if sort == "id":
        sort_column = Task.id
    elif sort == "name":
        sort_column = Task.name
    elif sort == "deadline":
        sort_column = Task.deadline
    else:
        sort_column = Task.id

    if order == "desc":
        sort_column = sort_column.desc()

    # 自分の完了タスク
    my_tasks = Task.query.filter_by(user=current_user, is_completed=True).order_by(sort_column).all()

    tracked_tasks = (
        Task.query.filter(
            Task.user_id == current_user.id,
            Task.is_tracked == True,
            Task.is_completed == True,
        )
        .order_by(sort_column)
        .all()
    )

    # 共有完了タスク
    shared_tasks = (
        Task.query.filter(
            Task.user_id.in_([f.id for f in list(current_user.followees) + [current_user]]),
            Task.is_shared == True,
            Task.is_completed == True,
        )
        .order_by(sort_column)
        .all()
    )

    return render_template(
        "completed.html",
        title="完了タスク一覧",
        my_tasks=my_tasks,
        tracked_tasks=tracked_tasks,
        shared_tasks=shared_tasks,
        sort=sort,  # ← テンプレートに渡す
        order=order,  # ← テンプレートに渡す
    )


@app.route("/completed_full", methods=["GET", "POST"])
@login_required
def completed_full():
    sort = request.args.get("sort", "deadline")  # デフォルトは締切日時
    order = request.args.get("order", "asc")  # デフォルトは昇順

    # 並び替え対象を決定
    if sort == "id":
        sort_column = Task.id
    elif sort == "name":
        sort_column = Task.name
    elif sort == "deadline":
        sort_column = Task.deadline
    else:
        sort_column = Task.id

    if order == "desc":
        sort_column = sort_column.desc()

    # 自分の完了タスク
    my_tasks = Task.query.filter_by(user=current_user, is_completed=True).order_by(sort_column).all()

    tracked_tasks = (
        Task.query.filter(
            Task.user_id == current_user.id,
            Task.is_tracked == True,
            Task.is_completed == True,
        )
        .order_by(sort_column)
        .all()
    )

    # 共有完了タスク
    shared_tasks = (
        Task.query.filter(
            Task.user_id.in_([f.id for f in list(current_user.followees) + [current_user]]),
            Task.is_shared == True,
            Task.is_completed == True,
        )
        .order_by(sort_column)
        .all()
    )

    return render_template(
        "completed_full.html",
        title="完了タスク一覧",
        my_tasks=my_tasks,
        tracked_tasks=tracked_tasks,
        shared_tasks=shared_tasks,
        sort=sort,  # ← テンプレートに渡す
        order=order,  # ← テンプレートに渡す
    )


@app.route("/incompleted", methods=["GET", "POST"])
@login_required
def incompleted():
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst).replace(tzinfo=None)

    sort = request.args.get("sort", "deadline")
    order = request.args.get("order", "asc")

    if sort == "id":
        sort_column = Task.id
    elif sort == "name":
        sort_column = Task.name
    elif sort == "deadline":
        sort_column = Task.deadline
    else:
        sort_column = Task.id

    if order == "desc":
        sort_column = sort_column.desc()

    my_tasks = Task.query.filter_by(user=current_user, is_completed=False).order_by(sort_column).all()

    tracked_tasks = (
        Task.query.filter(
            Task.user_id == current_user.id,
            Task.is_tracked == True,
            Task.is_completed == False,
        )
        .order_by(sort_column)
        .all()
    )

    shared_tasks = (
        Task.query.filter(
            Task.user_id.in_([f.id for f in list(current_user.followees) + [current_user]]),
            Task.is_shared == True,
            Task.is_completed == False,
        )
        .order_by(sort_column)
        .all()
    )

    for task in my_tasks + shared_tasks:
        if task.deadline:
            if task.deadline < now:
                task.is_overdue = True
            elif task.deadline <= now + timedelta(days=7):
                task.is_due_soon = True

    return render_template(
        "incompleted.html",
        title="未完了タスク一覧",
        my_tasks=my_tasks,
        tracked_tasks=tracked_tasks,
        shared_tasks=shared_tasks,
        sort=sort,
        order=order,
    )


@app.route("/incompleted_full", methods=["GET", "POST"])
@login_required
def incompleted_full():
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst).replace(tzinfo=None)

    sort = request.args.get("sort", "deadline")
    order = request.args.get("order", "asc")

    if sort == "id":
        sort_column = Task.id
    elif sort == "name":
        sort_column = Task.name
    elif sort == "deadline":
        sort_column = Task.deadline
    else:
        sort_column = Task.id

    if order == "desc":
        sort_column = sort_column.desc()

    my_tasks = Task.query.filter_by(user=current_user, is_completed=False).order_by(sort_column).all()

    tracked_tasks = (
        Task.query.filter(
            Task.user_id == current_user.id,
            Task.is_tracked == True,
            Task.is_completed == False,
        )
        .order_by(sort_column)
        .all()
    )

    shared_tasks = (
        Task.query.filter(
            Task.user_id.in_([f.id for f in list(current_user.followees) + [current_user]]),
            Task.is_shared == True,
            Task.is_completed == False,
        )
        .order_by(sort_column)
        .all()
    )

    for task in my_tasks + shared_tasks:
        if task.deadline:
            if task.deadline < now:
                task.is_overdue = True
            elif task.deadline <= now + timedelta(days=7):
                task.is_due_soon = True

    return render_template(
        "incompleted_full.html",
        title="未完了タスク一覧",
        my_tasks=my_tasks,
        tracked_tasks=tracked_tasks,
        shared_tasks=shared_tasks,
        sort=sort,
        order=order,
    )


@app.route("/update/<int:task_id>", methods=["GET", "POST"])
@login_required
def update(task_id):  # URL末尾のtask_idを引数task_idとして受け取る
    next_url = request.form.get("next") or "/"
    task = Task.query.get(task_id)  # どちらのメソッドでも共通して行う処理
    # タスクが存在しないかログインしているユーザのものでない場合，タスク一覧に移動
    if task is None or task.user != current_user:
        flash("存在しないタスクです")
        return redirect(next_url)  # 元ページに戻る。なければ"/"

    if request.method == "GET":  # GETメソッドのときの処理
        return render_template("update.html", title="更新", task=task, old_task=task)

    name = request.form["name"]
    deadline_raw = request.form["deadline"]

    # 入力チェック
    if not name and not deadline_raw:
        flash("タスク名と締切日時が入力されていません")
        return redirect(f"/update/{task_id}")
    elif not name:
        flash("タスク名を入力してください")
        return redirect(f"/update/{task_id}")
    elif not deadline_raw:
        flash("締切日時を入力してください")
        return redirect(f"/update/{task_id}")

    try:
        deadline = datetime.strptime(deadline_raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("締切日時の形式が正しくありません")
        return redirect(f"/update/{task_id}")

    # POSTメソッドのときの処理
    task.name = request.form["name"]  # フォームの内容でタスク名を更新
    task.deadline = deadline  # フォームの内容で締切日時を更新
    task.is_shared = request.form.get("is_shared") is not None  # フォームの内容で共有フラグを更新
    task.is_completed = request.form.get("is_completed") is not None  # フォームの内容で完了フラグを更新
    task.is_tracked = request.form.get("is_tracked") is not None  # フォームの内容で追跡フラグを更新
    db.session.commit()  # 更新をDBに反映
    return redirect(next_url)


@app.route("/delete/<int:task_id>", methods=["GET", "POST"])
@login_required
def delete(task_id):
    # POSTリクエスト時にフォームから送信された次のURLを取得するが、今回は未使用
    next_url = request.form.get("next") or "/"
    task = Task.query.get(task_id)

    # タスクが存在しないかログインしているユーザのものでない場合
    if task is None or task.user != current_user:
        flash("存在しないタスクです", "danger")  # フラッシュメッセージにカテゴリを追加

        # 不正なアクセスの場合、念のためホームに戻す
        return redirect(next_url)

    # GETメソッドのときの処理 (削除確認ページの表示)  # noqa: ERA001
    if request.method == "GET":
        # 戻るボタンのリンク先: request.referrerがなければホーム('/')をデフォルトとする
        back_url = request.referrer if request.referrer and request.referrer != request.url else url_for("index")

        return render_template(
            "delete.html",
            title="削除",
            task=task,
            back_url=back_url,  # 戻るボタンのリンク先
        )

    # POSTメソッドのときの処理 (削除実行)  # noqa: ERA001
    # 削除操作が実行される前にタスク名を保存しておく
    task_name = task.name

    db.session.delete(task)
    db.session.commit()

    flash(f"{task_name} を削除しました。", "success")  # 成功メッセージ

    return redirect(next_url)


@app.route("/delete_multiple", methods=["POST"])
@login_required
def delete_multiple():
    # フォームから "task_ids" という名前のチェックボックスの値をリストで取得
    ids_to_delete = request.form.getlist("task_ids")

    if not ids_to_delete:
        flash("削除するタスクが選択されていません")
        return redirect(request.referrer or "/")  # 元ページに戻る。なければ"/"

    # 削除対象のIDリストを使い、かつ自分のタスクであるものだけをDBから取得
    tasks = Task.query.filter(Task.id.in_(ids_to_delete), Task.user == current_user).all()

    # 取得したタスクを削除
    for task in tasks:
        db.session.delete(task)

    # 削除をDBに反映
    db.session.commit()

    flash(f"{len(tasks)}件のタスクを削除しました")
    return redirect(request.referrer or "/")


def get_tasks(query, user_id, completed=False, incompleted=False):
    # 自分のタスク
    my_filter = [Task.user_id == user_id, Task.name.like(f"%{query}%")]
    if completed:
        my_filter.append(Task.is_completed == True)
    elif incompleted:
        my_filter.append(Task.is_completed == False)
    my_tasks = Task.query.filter(*my_filter).all()

    # 追跡タスク
    tracked_filter = [Task.user_id == user_id, Task.is_tracked == True, Task.name.like(f"%{query}%")]
    if completed:
        tracked_filter.append(Task.is_completed == True)
    elif incompleted:
        tracked_filter.append(Task.is_completed == False)
    tracked_tasks = Task.query.filter(*tracked_filter).all()

    # 共有タスク
    shared_filter = [Task.user_id != user_id, Task.is_shared == True, Task.name.like(f"%{query}%")]
    if completed:
        shared_filter.append(Task.is_completed == True)
    elif incompleted:
        shared_filter.append(Task.is_completed == False)
    shared_tasks = Task.query.filter(*shared_filter).all()

    return my_tasks, tracked_tasks, shared_tasks


@app.route("/search")
@login_required
def search():
    query = request.args.get("q", "").strip()
    template = request.args.get("template", "index.html")  # 呼び出し元を受け取る

    if not query:
        return redirect(url_for(template.replace(".html", "")))

    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst).replace(tzinfo=None)

    # completed.html の場合は completed=True
    completed = template in ["completed.html", "completed_full.html"]
    incompleted = template in ["incompleted.html", "incompleted_full.html"]

    my_tasks, tracked_tasks, shared_tasks = get_tasks(query, current_user.id, completed, incompleted)

    for task in my_tasks + shared_tasks + tracked_tasks:
        if task.deadline:
            if task.deadline < now:
                task.is_overdue = True
            elif task.deadline <= now + timedelta(days=7):
                task.is_due_soon = True

    return render_template(
        template,
        my_tasks=my_tasks,
        tracked_tasks=tracked_tasks,
        shared_tasks=shared_tasks,
        search_query=query,
        now=now,
    )


@app.route("/search_user")
@login_required
def search_user():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect("/users")

    my_users = User.query.filter(
        User.id != current_user.id,
        or_(User.lastname.ilike(f"%{query}%"), User.firstname.ilike(f"%{query}%"), User.id.ilike(f"%{query}%")),
    ).all()

    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst).replace(tzinfo=None)

    return render_template("users.html", users=my_users, search_query=query, now=now)


@app.route("/users")
@login_required
def users():
    users = User.query.all()
    users.remove(current_user)  # 自身を除く
    return render_template("users.html", title="ユーザ一覧", users=users)


@app.route("/follow/<string:user_id>")
@login_required
def follow(user_id):
    user = User.query.get(user_id)  # フォローしようとしているユーザ
    if current_user not in user.followers:  # まだフォローしていないなら
        user.followers.append(current_user)  # ユーザのフォロワーに追加
        db.session.commit()  # DBに反映
        flash("フォローしました")
    else:
        flash("既にフォローしています")
    return redirect("/users")


@app.route("/unfollow/<string:user_id>")
@login_required
def unfollow(user_id):
    user = User.query.get(user_id)  # フォロー解除しようとしているユーザ
    if current_user in user.followers:  # フォローしているなら
        current_user.followees.remove(user)  # ユーザのフォロワーから削除
        db.session.commit()  # DBに反映
        flash("フォローを解除しました")
    else:
        flash("フォローしていません")
    return redirect("/users")
