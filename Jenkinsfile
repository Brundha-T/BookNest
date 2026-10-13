
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
                bat '"C:\\Users\\Asus\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" --version'
                bat '"C:\\Users\\Asus\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" -m pip install -r requirements.txt'
                bat '"C:\\Users\\Asus\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" -m pytest -q'
            }
        }

        stage('Build Docker Image') {
            steps {
                bat '"C:\\Users\\Asus\\AppData\\Local\\Programs\\DockerDesktop\\resources\\bin\\docker.exe" build -t booknest:latest .'
            }
        }

        stage('Deploy with Ansible') {
            steps {
                bat 'wsl.exe -d Ubuntu --cd /mnt/d/BookNest ansible-playbook -i ansible/inventory.ini ansible/deploy.yml'
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
