pipeline {
    agent any
    stages {
        stage('Checkout') { steps { checkout scm } }
        stage('Install and Test') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install -r requirements.txt
                    pytest -q
                '''
            }
        }
        stage('Build Docker Image') {
            steps { sh 'docker build -t booknest:latest .' }
        }
        stage('Deploy with Ansible') {
            steps { sh 'ansible-playbook -i ansible/inventory.ini ansible/deploy.yml' }
        }
    }
    post {
        success { echo 'BookNest pipeline completed successfully.' }
        failure { echo 'Pipeline failed; inspect the console output.' }
    }
}
