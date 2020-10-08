import csv
import json

from lxml import etree
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


class Logger:

    def __init__(self):
        self.log = {}

    def log_operation(self, profile_link, log_line):
        if profile_link not in self.log:
            self.log[profile_link] = []

        self.log[profile_link].append(log_line)

    def save_as_xml(self):
        root = etree.Element('data')
        for profile_id in self.log:
            profile_el = etree.SubElement(root, "profile")
            link = etree.SubElement(profile_el, "link")
            link.text = f"profile_id={profile_id}"
            for profile_ach in self.log[profile_id]:
                achiv_el = etree.SubElement(profile_el, "achievement")
                achiv_el.text = profile_ach

        tree = etree.ElementTree(root)
        tree.write("work_log.xml", pretty_print=True, xml_declaration=True, encoding="utf-8")


class SchoolHandler:
    def __init__(self, logger_instance):
        chrome_options = Options()
        chrome_options.add_argument("user-data-dir=selenium_data")
        self.driver = webdriver.Chrome(ChromeDriverManager().install())
        self.logger = logger_instance

    def login_sequence(self, login, password):
        self.driver.get("https://login.dnevnik.ru/login")
        try:
            WebDriverWait(self.driver, 3).until(expected_conditions.presence_of_element_located(
                (By.XPATH, "/html/body/div/div/div/div/div/form/div[2]/div[3]/div[5]/div[2]/button"))).click()
        except TimeoutException as ex:
            print("First login")

        login_input = self.driver.find_element_by_name("login")
        login_input.send_keys(login)
        pass_input = self.driver.find_element_by_name("password")
        pass_input.send_keys(password)
        WebDriverWait(self.driver, 3).until(expected_conditions.presence_of_element_located(
            (By.CLASS_NAME, "login__submit"))).click()

    def get_profiles_from_page(self, page):
        self.driver.get("https://schools.dnevnik.ru/school.aspx?school=1172&view=members&group=students&page=" + page)
        profiles_ids = []
        for profiles_page_link_container in self.driver.find_elements_by_class_name("tdButtons"):
            try:
                profile_page_link = profiles_page_link_container. \
                    find_element_by_class_name("iE"). \
                    find_element_by_tag_name('a')
            except NoSuchElementException:
                continue

            profile_page_link = profile_page_link.get_attribute("href")
            profile_page_link = profile_page_link.split("=")[1]
            profile_page_link = profile_page_link.split("&")[0]
            profiles_ids.append(profile_page_link)

        return profiles_ids

    def get_total_profiles_pages(self):
        self.driver.get("https://schools.dnevnik.ru/school.aspx?school=1172&view=members&group=students")
        pager = self.driver.find_element_by_class_name("pager")
        last_page = pager.find_elements_by_tag_name("li")[-1]
        return last_page.text

    def go_to_achievements_page(self, profile_link):
        achievements_link = f"https://schools.dnevnik.ru/admin/persons/person.aspx?person={profile_link}&" \
                            f"school=1172&view=achievements"
        self.driver.get(achievements_link)

    def process_profile_bonuses(self, profile_link):
        for achievement in self.get_next_achievements():
            ach_name = achievement.find_elements_by_tag_name("td")[0].text
            ach_result = achievement.find_elements_by_tag_name("td")[1].text
            ach_helper = AchievementHelper()
            if ach_helper.is_result_exception(ach_result):
                log_line = f"Достижение '{ach_name}' не нуждается в редактировании"
                self.logger.log_operation(profile_link=profile_link, log_line=log_line)
                continue

            if ach_helper.is_manual_case(ach_name):
                log_line = f"Достижение '{ach_name}', отмечено для ручной проверки - особый случай"
                self.logger.log_operation(profile_link=profile_link, log_line=log_line)
                continue

            try:
                new_result = ach_helper.get_new_result(ach_name)
            except ValueError:
                log_line = f"Нет правил для достижения '{ach_name}', отмечено для ручной проверки"
                self.logger.log_operation(profile_link=profile_link, log_line=log_line)
                continue

            self.update_result(achievement, new_result)
            log_line = f"Результат достижения '{ach_name}' будет заменен на '{new_result}'"
            self.logger.log_operation(profile_link=profile_link, log_line=log_line)

    def get_next_achievements(self):
        achievements_list = self.driver.find_element_by_id("mtabl") \
            .find_element_by_tag_name("tbody") \
            .find_elements_by_tag_name("tr")
        for achievement in achievements_list:
            yield achievement

    def is_current_page_has_achievements(self):
        try:
            self.driver.find_element_by_class_name("emptyData")
        except NoSuchElementException:
            return True
        return False

    def update_result(self, achievement, new_result):
        options_btn = WebDriverWait(achievement, 5).until(expected_conditions.element_to_be_clickable(
            (By.LINK_TEXT, "Подробнее...")))
        from time import sleep
        sleep(1)
        options_btn.click()
        edit_btn = WebDriverWait(self.driver, 5).until(expected_conditions.element_to_be_clickable(
            (By.CSS_SELECTOR, "a.modalEdit")))
        edit_btn.click()
        result_input = WebDriverWait(self.driver, 5).until(expected_conditions.presence_of_element_located(
            (By.ID, "achResult")))
        result_input.clear()
        result_input.send_keys(new_result)
        save_btn = self.driver.find_element_by_css_selector("a.modalSave")
        save_btn.click()

    def get_to_achievement_page(self, page_link):
        self.driver.get(page_link)

    def add_achievement(self, achievement_name, event_type, event_level, achievement_area, event_date, event_result,
                        event_proof):
        # open modal
        options_btn = WebDriverWait(self.driver, 5).until(expected_conditions.element_to_be_clickable(
            (By.LINK_TEXT, "Добавить достижение")))
        options_btn.click()

        # result
        name_input = WebDriverWait(self.driver, 5).until(expected_conditions.presence_of_element_located(
            (By.ID, "achName")))
        name_input.send_keys(achievement_name)

        # event_type
        select = Select(self.driver.find_element_by_id('achType'))
        select.select_by_visible_text(event_type)

        # event_level
        select = Select(self.driver.find_element_by_id('achLevel'))
        select.select_by_visible_text(event_level)

        # achievement_area
        # TODO fix that damn input
        select = Select(self.driver.find_element_by_name('achArea'))
        select.select_by_visible_text(achievement_area)

        # event_date
        result_input = WebDriverWait(self.driver, 5).until(expected_conditions.presence_of_element_located(
            (By.ID, "achievementdate")))
        result_input.send_keys(event_date)

        # event_result
        result_input = WebDriverWait(self.driver, 5).until(expected_conditions.presence_of_element_located(
            (By.ID, "achResult")))
        result_input.send_keys(event_result)

        # event_proof
        result_input = WebDriverWait(self.driver, 5).until(expected_conditions.presence_of_element_located(
            (By.ID, "achDoc")))
        result_input.send_keys(event_proof)

        # close modal
        # TODO CHange to Сохранить
        options_btn = WebDriverWait(self.driver, 5).until(expected_conditions.element_to_be_clickable(
            (By.LINK_TEXT, "Отмена")))
        options_btn.click()

    def quit(self):
        self.driver.quit()


if __name__ == '__main__':
    logger = Logger()
    school_handler = SchoolHandler(logger_instance=logger)

    with open('credentials') as json_file:
        credential_data = json.load(json_file)
        school_handler.login_sequence(credential_data["login"], credential_data["password"])

    with open('to_do_list.csv', newline='') as csv_file:
        reader = csv.reader(csv_file, delimiter=',', quotechar='|')
        for row in reader:
            school_handler.get_to_achievement_page(page_link=row[1])
            school_handler.add_achievement(
                achievement_name=row[2],
                event_type=row[3],
                event_level=row[4],
                achievement_area=row[5],
                event_date=row[6],
                event_result=row[7],
                event_proof=row[8],
            )
            print(row)

    school_handler.quit()
    logger.save_as_xml()
