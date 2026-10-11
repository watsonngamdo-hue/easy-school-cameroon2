const url = window.location.href
const quizContainer = document.getElementById('quiz-container')
const quizBox = document.getElementById('quiz-box')
const scoreVal = document.getElementById('score-val')
const scoreCircle = document.getElementById('score-circle')
const resultTitle = document.getElementById('result-title')
const resultMsg = document.getElementById('result-msg')
const resultDetails = document.getElementById('result-details')
const timerBox = document.getElementById('timer-box')
const progressBar = document.getElementById('progress-bar')
const progressText = document.getElementById('progress-text')
const progressPercent = document.getElementById('progress-percent')

const quizForm = document.getElementById('quiz-form')
const prevBtn = document.getElementById('prev-btn')
const nextBtn = document.getElementById('next-btn')
const submitBtn = document.getElementById('submit-btn')
const resultsContainer = document.getElementById('results-container')
const csrf = document.getElementsByName('csrfmiddlewaretoken')

let currentIndex = 0
let numQuestions = 0

const activateTimer = (time) => {
    let minutes = time - 1
    let seconds = 60
    let displaySeconds
    let displayMinutes

    const timer = setInterval(() => {
        seconds--
        if (seconds < 0) {
            seconds = 59
            minutes--
        }
        displayMinutes = minutes.toString().padStart(2, '0')
        displaySeconds = seconds.toString().padStart(2, '0')

        if (minutes === 0 && seconds === 0) {
            timerBox.innerHTML = `<i class="material-icons" style="font-size: 20px; color: #ef4444;">timer_off</i><b>00:00</b>`
            clearInterval(timer)
            setTimeout(() => {
                alert('Temps écoulé ! Vos réponses vont être envoyées.')
                sendData()
            }, 500)
        }

        timerBox.querySelector('span').innerText = `${displayMinutes}:${displaySeconds}`
    }, 1000)
}

const updateView = () => {
    const steps = document.querySelectorAll('.question-step')
    steps.forEach((step, index) => {
        if (index === currentIndex) {
            step.classList.remove('not-visible')
        } else {
            step.classList.add('not-visible')
        }
    })

    // Navigation buttons
    if (currentIndex === 0) {
        prevBtn.classList.add('not-visible')
    } else {
        prevBtn.classList.remove('not-visible')
    }

    if (currentIndex === numQuestions - 1) {
        nextBtn.classList.add('not-visible')
        submitBtn.classList.remove('not-visible')
    } else {
        nextBtn.classList.remove('not-visible')
        submitBtn.classList.add('not-visible')
    }

    // Progress bar
    const progress = ((currentIndex + 1) / numQuestions) * 100
    progressBar.style.width = `${progress}%`
    progressText.innerText = `Question ${currentIndex + 1} sur ${numQuestions}`
    progressPercent.innerText = `${Math.round(progress)}%`
}

$.ajax({
    type: 'GET',
    url: `${url}data`,
    success: function(response) {
        const data = response.data
        numQuestions = data.length
        quizBox.innerHTML = '' // Clear loading state

        data.forEach((el, index) => {
            for (const [question, answers] of Object.entries(el)) {
                const step = document.createElement('div')
                step.className = 'question-step'
                if (index !== 0) step.classList.add('not-visible')

                step.innerHTML = `
                    <div class="question-title">${question}</div>
                    <div class="options-grid">
                        ${answers.map((answer, i) => `
                            <div class="option-item">
                                <input type="radio" class="option-input ans" id="${index}-${i}" name="${question}" value="${answer}">
                                <label class="option-label" for="${index}-${i}">${answer}</label>
                            </div>
                        `).join('')}
                    </div>
                `
                quizBox.appendChild(step)
            }
        })

        activateTimer(response.time)
        updateView()
    },
    error: function(error) {
        console.log(error)
        quizBox.innerHTML = '<p class="text-danger text-center">Erreur lors du chargement des données du quiz.</p>'
    }
})

nextBtn.addEventListener('click', () => {
    if (currentIndex < numQuestions - 1) {
        currentIndex++
        updateView()
    }
})

prevBtn.addEventListener('click', () => {
    if (currentIndex > 0) {
        currentIndex--
        updateView()
    }
})

const sendData = () => {
    const elements = [...document.getElementsByClassName('ans')]
    const data = {}
    data['csrfmiddlewaretoken'] = csrf[0].value
    
    elements.forEach(el => {
        if (el.checked) {
            data[el.name] = el.value
        } else {
            if (!data[el.name]) {
                data[el.name] = null
            }
        }
    })

    $.ajax({
        type: 'POST',
        url: `${url}save/`,
        data: data,
        success: function(response) {
            quizContainer.classList.add('not-visible')
            resultsContainer.classList.remove('not-visible')
            timerBox.classList.add('not-visible')

            const score = response.score.toFixed(2)
            scoreVal.innerText = `${score}%`
            
            if (response.passed) {
                resultTitle.innerText = "Félicitations !"
                resultTitle.style.color = "#10b981"
                resultMsg.innerText = "Vous avez réussi cet examen avec succès. Votre maîtrise du sujet est remarquable."
                scoreCircle.style.borderColor = "#10b981"
            } else {
                resultTitle.innerText = "Continuez vos efforts !"
                resultTitle.style.color = "#ef4444"
                resultMsg.innerText = "Vous n'avez pas atteint le score minimum requis. Repassez la leçon et réessayez !"
                scoreCircle.style.borderColor = "#ef4444"
            }

            resultDetails.innerHTML = '<h5 class="m-b-2 font-weight-bold">Détails des réponses :</h5>'
            
            response.results.forEach((res, index) => {
                const resDiv = document.createElement("div")
                resDiv.className = 'result-item'

                for (const [question, resp] of Object.entries(res)) {
                    if (resp === 'not answered') {
                        resDiv.classList.add('result-incorrect')
                        resDiv.innerHTML = `
                            <div class="font-weight-bold">${index + 1}. ${question}</div>
                            <div class="small m-t-1">Statut : Non répondu</div>
                        `
                    } else {
                        const answer = resp['answered']
                        const correct = resp['correct_answer']

                        if (answer === correct) {
                            resDiv.classList.add('result-correct')
                            resDiv.innerHTML = `
                                <div class="font-weight-bold">${index + 1}. ${question}</div>
                                <div class="small m-t-1">Votre réponse : ${answer} <span class="badge badge-success ml-2">Correct</span></div>
                            `
                        } else {
                            resDiv.classList.add('result-incorrect')
                            resDiv.innerHTML = `
                                <div class="font-weight-bold">${index + 1}. ${question}</div>
                                <div class="small m-t-1">Votre réponse : ${answer} <span class="badge badge-danger ml-2">Incorrect</span></div>
                                <div class="small font-weight-bold m-t-1" style="color: #166534">Bonne réponse : ${correct}</div>
                            `
                        }
                    }
                }
                resultDetails.appendChild(resDiv)
            })

            window.scrollTo({ top: 0, behavior: 'smooth' })
        },
        error: function(error) {
            console.log(error)
            alert("Une erreur est survenue lors de l'envoi de vos réponses.")
        }
    })
}

quizForm.addEventListener('submit', e => {
    e.preventDefault()
    sendData()
})