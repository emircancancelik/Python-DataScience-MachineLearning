from abc import ABC, abstractmethod
from typing import final, override, overload, Union

# ---------------------------------------------------------
# 1. BASIC DECORATORS (Fonksiyonu değiştirmeden özellik ekleme)
# ---------------------------------------------------------

def my_decorator(func):
    def wrapper():
        print("--- Fonksiyon çalışmadan önceki işlemler ---")
        func()
        print("--- Fonksiyon bittikten sonraki işlemler ---")
    return wrapper

@my_decorator
def say_hello():
    print("Merhaba dünya!")

# Deneme yapıyorum
say_hello()


# Argüman alan decorator örneği
def repeat_three_times(func):
    def wrapper(*args, **kwargs):
        for i in range(3):
            print(f"{i+1}. kez çalışıyor:")
            func(*args, **kwargs)
    return wrapper

@repeat_three_times
def greet(name):
    print(f"Selam {name}")

greet("Emircan")


# ---------------------------------------------------------
# 2. PROPERTY DECORATORS (Getter/Setter mantığı)
# ---------------------------------------------------------

class Person:
    def __init__(self, name, age):
        self.__name = name  # private değişken
        self.__age = age

    @property  # Okuma yaparken (getter)
    def name(self):
        print("İsim getiriliyor...")
        return self.__name

    @name.setter  # Değer atarken (setter) - Validation burada yapılır
    def name(self, value):
        print("İsim değiştiriliyor...")
        if not isinstance(value, str):
            raise ValueError("İsim metin olmalı!")
        self.__name = value

    @property
    def age(self):
        return self.__age

    @age.setter
    def age(self, value):
        if value < 0:
            raise ValueError("Yaş negatif olamaz")
        self.__age = value

    @property
    def is_adult(self):  # Sadece okunabilir, setter'ı yok (Computed property)
        return self.__age >= 18

p = Person("Ali", 25)
print(p.name)       # property sayesinde parantezsiz çağırıyoruz
p.name = "Veli"     # setter çalışır
print(f"Yetişkin mi: {p.is_adult}")


# ---------------------------------------------------------
# 3. STATIC & CLASS METHODS
# ---------------------------------------------------------

class MathOps:
    # self veya cls almaz, sınıf içinde duran düz fonksiyon gibi
    @staticmethod
    def add(x, y):
        return x + y

print(f"Toplam: {MathOps.add(5, 10)}")


class Pizza:
    def __init__(self, ingredients):
        self.ingredients = ingredients

    def __repr__(self):
        return f"Pizza({self.ingredients})"

    # cls parametresi alır, genelde "alternative constructor" olarak kullanılır
    @classmethod
    def margherita(cls):
        return cls(['mozzarella', 'domates', 'fesleğen'])
    
    @classmethod
    def pepperoni(cls):
        return cls(['mozzarella', 'sucuk'])

p1 = Pizza(['mantar', 'biber']) # Normal kullanım
p2 = Pizza.margherita()         # Factory method kullanımı
print(p1)
print(p2)


# ---------------------------------------------------------
# 4. ABSTRACT METHODS (Şablon oluşturma)
# ---------------------------------------------------------

class Animal(ABC):
    @abstractmethod
    def make_sound(self):
        pass  # Alt sınıflar bunu KESİN doldurmak zorunda

class Dog(Animal):
    def make_sound(self):
        print("Hav hav!")

class Cat(Animal):
    def make_sound(self):
        print("Miyav!")

dog = Dog()
dog.make_sound()

# animal = Animal() # HATA verir, abstract class direkt çağrılmaz


# ---------------------------------------------------------
# 5. FINAL & OVERRIDE & OVERLOAD (Tip güvenliği ve kısıtlamalar)
# ---------------------------------------------------------

# @final: Bu sınıf miras alınamaz veya bu metot ezilemez (override edilemez)
class BaseGame:
    @final
    def calculate_score(self, points):
        return points * 10  # Bu mantığı alt sınıflar değiştiremesin istiyorum

class MyGame(BaseGame):
    # @override: Python 3.12+ özelliği. Yanlışlıkla metod ismini hatalı yazarsam uyarır.
    @override 
    def calculate_score(self, points): # IDE burada hata gösterir çünkü parent'ta @final var
        return points * 20

# @overload: Sadece type-hinting için. Fonksiyonun farklı parametrelerle nasıl davranacağını IDE'ye söyler.
# Gerçek kod çalışırken en alttaki implementation çalışır.
class Calculator:
    @overload
    def process(self, x: int) -> int: ...
    
    @overload
    def process(self, x: str) -> str: ...

    def process(self, x):
        if isinstance(x, int):
            return x * 2
        elif isinstance(x, str):
            return x.upper()

calc = Calculator()
print(calc.process(10))
print(calc.process("hello"))