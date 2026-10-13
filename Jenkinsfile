pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install and Test') {
            steps {
                bat 'python --version'
                bat 'python -m pip install -r requirements.txt'
                bat 'python -m pytest -q'
            }
        }

        stage('Build Docker Image') {
            steps {
                bat 'docker build -t booknest:latest .'
            }
        }
    }

    post {
        success {
            echo 'BookNest pipeline completed successfully.'
        }
        failure {
            echo 'Pipeline failed; inspect the console output.'
        }
    }
}