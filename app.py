from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'super_secret_key_datastock'

# Base de datos simulada (para avanzar funcionalidad inicial)
users_db = {'admin': 'admin123', 'gerente': 'gerente2026'}
inventory = [{'id': 1, 'nombre': 'Takis', 'cantidad': 29}, {'id': 2, 'nombre': 'Arroz Kg', 'cantidad': 45}]

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in users_db and users_db[username] == password:
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciales incorrectas. Intente nuevamente.')
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    # Funcionalidad extra: Mostrar inventario inicial tras el login exitoso
    return f"<h1>Bienvenido a DataStock</h1><p>Inventario actual: {inventory}</p>"

if __name__ == '__main__':
    app.run(debug=True)
